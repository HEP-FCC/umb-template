"""
Entity operations functionality for the Database class.

This module handles entity updates, deletions, and bulk override operations
with support for field locking and metadata management.
"""

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.storage.database import Database

import asyncpg

from app.storage.schema_discovery import get_schema_discovery
from app.utils.logging_utils import get_logger
from app.utils.uuid_utils import generate_entity_uuid

logger = get_logger()


async def update_entity(
    database: "Database",
    entity_id: int,
    update_data: dict[str, Any],
    user_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Update an entity with the provided data using full replacement strategy.
    Returns the updated entity with all details.
    """
    main_table = database.config["application"]["main_table"]

    async with database.session() as conn:
        primary_key_column = await _get_main_table_primary_key(conn, main_table)

        async with conn.transaction():
            await _validate_entity_exists(
                conn, entity_id, primary_key_column, main_table
            )

            update_fields, values = await _prepare_update_fields(
                conn,
                update_data,
                main_table,
                primary_key_column,
                entity_id,
                user_info,
            )

            await _execute_update_query(
                conn,
                update_fields,
                values,
                entity_id,
                primary_key_column,
                main_table,
            )

            # Return the updated entity - import here to avoid circular imports
            from app.storage.database_modules.entity_retrieval_module import (
                get_entity_by_id,
            )

            updated_entity = await get_entity_by_id(database, entity_id)
            if not updated_entity:
                raise RuntimeError(f"Failed to retrieve updated entity {entity_id}")

            return updated_entity


async def delete_entities_by_ids(
    database: "Database", entity_ids: list[int]
) -> dict[str, Any]:
    """
    Delete entities by their IDs from the database.
    Returns a summary of the deletion operation.
    """
    if not entity_ids:
        return {
            "success": True,
            "deleted_count": 0,
            "not_found_count": 0,
            "message": "No entity IDs provided for deletion",
        }

    main_table = database.config["application"]["main_table"]

    async with database.session() as conn:
        # Get the primary key column dynamically
        primary_key_column = await _get_main_table_primary_key(conn, main_table)

        async with conn.transaction():
            # First, check which entities exist
            placeholders = ",".join(f"${i + 1}" for i in range(len(entity_ids)))
            check_query = f"""
                SELECT {primary_key_column}
                FROM {main_table}
                WHERE {primary_key_column} IN ({placeholders})
            """

            existing_entities = await conn.fetch(check_query, *entity_ids)
            existing_ids = {row[primary_key_column] for row in existing_entities}

            not_found_ids = set(entity_ids) - existing_ids
            not_found_count = len(not_found_ids)

            if not existing_ids:
                return {
                    "success": True,
                    "deleted_count": 0,
                    "not_found_count": not_found_count,
                    "message": "No entities found with the provided IDs",
                    "not_found_ids": list(not_found_ids),
                }

            # Delete the entities
            existing_ids_list = list(existing_ids)
            delete_placeholders = ",".join(
                f"${i + 1}" for i in range(len(existing_ids_list))
            )
            delete_query = f"""
                DELETE FROM {main_table}
                WHERE {primary_key_column} IN ({delete_placeholders})
            """

            try:
                result = await conn.execute(delete_query, *existing_ids_list)
                # Extract the count from the result (e.g., "DELETE 3")
                deleted_count = (
                    int(result.split()[-1])
                    if result.split()[-1].isdigit()
                    else len(existing_ids_list)
                )

                logger.info(
                    f"Successfully deleted {deleted_count} entities: {existing_ids_list}"
                )

                return {
                    "success": True,
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "message": f"Successfully deleted {deleted_count} entities",
                    "deleted_ids": existing_ids_list,
                    "not_found_ids": list(not_found_ids) if not_found_ids else None,
                }

            except asyncpg.ForeignKeyViolationError as e:
                logger.error(
                    f"Cannot delete entities due to foreign key constraints: {e}"
                )
                raise ValueError(
                    "Cannot delete entities as they are referenced by other records. "
                    "Please remove related records first."
                )
            except Exception as e:
                logger.error(f"Error deleting entities: {e}")
                raise RuntimeError(f"Failed to delete entities: {str(e)}")


async def bulk_override_entities(
    database: "Database",
    entities: list[dict[str, Any]],
    user_info: dict[str, Any] | None = None,
    force_override: bool = False,
) -> dict[str, Any]:
    """
    Bulk override entities with metadata-only updates, field locking and transaction management.

    This function is designed to ONLY update metadata fields. It will block attempts to update
    table columns such as foreign keys, names, UUIDs, or other database fields for security.

    REQUIRES: Each entity MUST include a valid 'uuid' field to identify the entity to update.
    No UUID computation is performed - entities without UUIDs will be rejected.

    When metadata is updated, the fuzzy search capabilities are automatically maintained
    through the database's expression index on jsonb_values_to_text(metadata).

    Args:
        entities: List of entity dictionaries to update - each MUST contain a 'uuid' field
        user_info: User information for audit logging
        force_override: If True, ignore field locks and force the metadata update

    Returns:
        Dictionary with operation results, including lock conflicts or missing UUIDs if any
    """
    main_table = database.config["application"]["main_table"]

    async with database.session() as conn:
        primary_key_column = await _get_main_table_primary_key(conn, main_table)

        # Use a transaction for atomicity
        async with conn.transaction():
            lock_conflicts = []
            entities_to_update = []
            missing_entities = []

            # Phase 1: Validate UUIDs and check locks
            for entity_data in entities:
                try:
                    # Require UUID for each entity
                    entity_uuid = entity_data.get("uuid")
                    if not entity_uuid:
                        # Track entities missing UUID
                        entity_identifier = entity_data.get("name", "unknown entity")
                        missing_entities.append(
                            {
                                "entity_data": entity_data,
                                "identifier": f"Missing UUID (name: {entity_identifier})",
                            }
                        )
                        continue

                    # Try to resolve entity by UUID only
                    resolved_entity = await _resolve_entity_by_uuid_only(
                        conn, entity_uuid, main_table, primary_key_column
                    )

                    if not resolved_entity:
                        # Track missing entities for error reporting
                        entity_identifier = entity_data.get(
                            "uuid", entity_data.get("name", "unknown")
                        )
                        missing_entities.append(
                            {
                                "entity_data": entity_data,
                                "identifier": entity_identifier,
                            }
                        )
                        continue  # Skip entities that can't be resolved

                    entity_id = resolved_entity["entity_id"]
                    entity_uuid = resolved_entity["entity_uuid"]

                    # Check for lock conflicts
                    current_entity = await _get_entity_with_metadata(
                        conn, entity_id, main_table, primary_key_column
                    )

                    if not current_entity:
                        continue

                    # Extract metadata and check locks for fields being updated
                    # Parse metadata if it's a string (JSON)
                    raw_metadata = current_entity.get("metadata", {})
                    if isinstance(raw_metadata, str):
                        try:
                            current_metadata = json.loads(raw_metadata)
                        except (json.JSONDecodeError, TypeError):
                            current_metadata = {}
                    elif isinstance(raw_metadata, dict):
                        current_metadata = raw_metadata
                    else:
                        current_metadata = {}

                    conflicted_fields = {}

                    # Only check for lock conflicts if force_override is False
                    if not force_override:
                        for field_name in entity_data.keys():
                            if field_name in ["uuid"]:  # Skip special fields
                                continue

                            lock_field_name = f"__{field_name}__lock__"
                            if current_metadata.get(lock_field_name):
                                conflicted_fields[field_name] = {
                                    "locked": True,
                                    "current_value": current_metadata.get(field_name),
                                    "attempted_value": entity_data[field_name],
                                }

                    if conflicted_fields and not force_override:
                        # Add to conflict list
                        lock_conflicts.append(
                            {
                                "entity_id": entity_id,
                                "entity_uuid": entity_uuid,
                                "locked_fields": conflicted_fields,
                                "entity_data": current_entity,
                            }
                        )
                    else:
                        # Add to update list (either no conflicts or force_override is True)
                        entities_to_update.append(
                            {
                                "entity_id": entity_id,
                                "entity_uuid": entity_uuid,
                                "update_data": entity_data,
                            }
                        )

                except Exception as e:
                    logger.error(f"Error processing entity {entity_data}: {e}")
                    continue

            # If any entities are missing UUIDs or not found, fail the entire transaction
            if missing_entities:
                missing_count = len(missing_entities)
                missing_details = []

                for missing in missing_entities:
                    missing_details.append(str(missing["identifier"]))

                # Transaction will automatically rollback
                return {
                    "success": False,
                    "message": f"Cannot override entities. {missing_count} entities have issues: {', '.join(missing_details[:5])}{'...' if missing_count > 5 else ''}",
                    "entities_processed": 0,
                    "missing_entities": missing_entities,
                }

            # If any lock conflicts and force_override is False, rollback and return conflicts
            if lock_conflicts and not force_override:
                # Transaction will automatically rollback
                return {
                    "success": False,
                    "message": f"Lock conflicts detected for {len(lock_conflicts)} entities. No changes were made.",
                    "entities_processed": 0,
                    "lock_conflicts": lock_conflicts,
                }

            # Phase 2: Apply updates and create locks
            updated_entities = []

            for entity_update in entities_to_update:
                try:
                    entity_id = entity_update["entity_id"]
                    update_data = entity_update["update_data"].copy()

                    # Remove UUID and other protected fields from update data
                    protected_fields = {
                        "uuid",
                        "created_at",
                        "updated_at",
                        "last_edited_at",
                        "edited_by_name",
                    }
                    # Create a new dict without protected fields to avoid modifying during iteration
                    update_data = {
                        field: value
                        for field, value in update_data.items()
                        if field not in protected_fields and not field.endswith("_id")
                    }

                    # Get valid table columns to identify what should NOT be updated
                    valid_columns = await get_valid_table_columns(conn, main_table)

                    # Block all table field updates except metadata - this function should ONLY update metadata
                    metadata_fields = {}
                    blocked_table_fields = []

                    for field_name, field_value in update_data.items():
                        if field_name in valid_columns and field_name != "metadata":
                            # This is a table field (not metadata) - block it
                            blocked_table_fields.append(field_name)
                            logger.warning(
                                f"Blocked attempt to update table field '{field_name}' via bulk override - this function only updates metadata"
                            )
                        else:
                            # This is a metadata field - allow it
                            metadata_fields[field_name] = field_value

                    if blocked_table_fields:
                        logger.warning(
                            f"Bulk override blocked table field updates: {blocked_table_fields}. Only metadata fields are allowed."
                        )

                    logger.info(
                        f"Metadata-only update - Metadata fields: {list(metadata_fields.keys())}, Blocked table fields: {blocked_table_fields}"
                    )

                    # Prepare the properly structured update data with ONLY metadata
                    structured_update_data: dict[str, Any] = {}

                    # Only process metadata fields - this ensures we only update the metadata column
                    if metadata_fields:
                        structured_update_data["metadata"] = {}

                        # Add the individual metadata fields
                        for field_name, field_value in metadata_fields.items():
                            structured_update_data["metadata"][field_name] = field_value

                        # Create locks for all metadata fields being updated
                        for field_name in metadata_fields.keys():
                            lock_field_name = f"__{field_name}__lock__"
                            structured_update_data["metadata"][lock_field_name] = True

                    logger.info(
                        f"Final structured metadata-only update data: {structured_update_data}"
                    )

                    # Skip update if no metadata fields to update
                    if not structured_update_data:
                        logger.info(
                            f"No metadata fields to update for entity {entity_id}, skipping"
                        )
                        continue

                    # Update the entity using existing update logic
                    update_fields, values = await _prepare_update_fields(
                        conn,
                        structured_update_data,
                        main_table,
                        primary_key_column,
                        entity_id,
                        user_info,
                        force_override,
                    )

                    await _execute_update_query(
                        conn,
                        update_fields,
                        values,
                        entity_id,
                        primary_key_column,
                        main_table,
                    )

                    # Get updated entity for response
                    updated_entity = await _get_entity_with_metadata(
                        conn, entity_id, main_table, primary_key_column
                    )

                    if updated_entity:
                        updated_entities.append(updated_entity)

                except Exception as e:
                    logger.error(
                        f"Error updating entity {entity_update['entity_id']}: {e}"
                    )
                    # On any error, let the transaction rollback
                    raise

            force_override_msg = " (force override enabled)" if force_override else ""
            logger.info(
                f"Successfully updated metadata for {len(updated_entities)} entities in bulk override operation{force_override_msg} by user {user_info.get('preferred_username', 'unknown') if user_info else 'unknown'}"
            )

            success_message = (
                f"Successfully updated metadata for {len(updated_entities)} entities"
            )
            if force_override:
                success_message += " with force override (bypassed field locks)"
            else:
                success_message += " with field locks applied"

            return {
                "success": True,
                "message": success_message,
                "entities_processed": len(updated_entities),
                "updated_entities": updated_entities,
            }


# Helper functions for entity operations


async def _validate_entity_exists(
    conn: asyncpg.Connection,
    entity_id: int,
    primary_key_column: str,
    main_table: str,
) -> None:
    """Validate that the entity exists before updating."""
    existing_check = await conn.fetchval(
        f"SELECT {primary_key_column} FROM {main_table} WHERE {primary_key_column} = $1",
        entity_id,
    )
    if not existing_check:
        raise ValueError(f"Entity with ID {entity_id} not found")


async def _prepare_update_fields(
    conn: asyncpg.Connection,
    update_data: dict[str, Any],
    main_table: str,
    primary_key_column: str,
    entity_id: int,
    user_info: dict[str, Any] | None = None,
    force_override: bool = False,
) -> tuple[list[str], list[Any]]:
    """Prepare update fields and values for the update query."""
    # Always update updated_at for any operation
    update_fields = ["updated_at = NOW()"]
    values: list[Any] = []
    param_count = 0
    has_unlocked_changes = False

    valid_columns = await get_valid_table_columns(conn, main_table)

    for field_name, field_value in update_data.items():
        if _should_skip_field(
            field_name, field_value, valid_columns, primary_key_column
        ):
            continue

        param_count += 1

        processed_value: Any
        if field_name == "metadata" and isinstance(field_value, dict):
            processed_value = await _process_metadata_field(
                conn,
                field_value,
                entity_id,
                main_table,
                primary_key_column,
                force_override,
            )
        else:
            # Use generic date parsing to handle any timestamp/date fields automatically
            from app.utils.parsing_utils import try_parse_date_value

            processed_value = try_parse_date_value(field_value)

        update_fields.append(f"{field_name} = ${param_count}")
        values.append(processed_value)
        has_unlocked_changes = True

    # Update last_edited_at only if:
    # 1. user_info is provided (indicating manual operation)
    # 2. AND there are actual field changes
    if user_info and has_unlocked_changes:
        update_fields.append("last_edited_at = NOW()")

        # Build editor name from user info
        editor_name = None
        if user_info.get("given_name") and user_info.get("family_name"):
            editor_name = (
                f"{user_info.get('given_name')} {user_info.get('family_name')}"
            )
        elif user_info.get("preferred_username"):
            editor_name = user_info.get("preferred_username")
        elif user_info.get("name"):  # Fallback for direct name field
            editor_name = user_info.get("name")

        if editor_name:
            param_count += 1
            update_fields.append(f"edited_by_name = ${param_count}")
            values.append(editor_name)

    return update_fields, values


async def get_valid_table_columns(
    conn: asyncpg.Connection, main_table: str
) -> set[str]:
    """Get valid column names for the table."""
    table_columns_query = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = $1 AND table_schema = 'public'
        ORDER BY ordinal_position
    """
    table_columns = await conn.fetch(table_columns_query, main_table)
    return {row["column_name"] for row in table_columns}


def _should_skip_field(
    field_name: str,
    field_value: Any,
    valid_columns: set[str],
    primary_key_column: str,
) -> bool:
    """Check if a field should be skipped during update."""
    # Skip fields that don't exist in the table
    if field_name not in valid_columns:
        return True

    # Skip primary key and auto-managed fields
    if field_name in [
        primary_key_column,
        "created_at",
        "updated_at",
        "last_edited_at",
    ]:
        return True

    # Skip None values for non-nullable fields (except explicit null updates)
    if field_value is None and field_name == "name":
        return True

    return False


async def _process_metadata_field(
    conn: asyncpg.Connection,
    field_value: dict[str, Any],
    entity_id: int,
    main_table: str,
    primary_key_column: str,
    force_override: bool = False,
) -> str:
    """Process metadata field with locked field handling."""
    current_metadata = await _get_current_metadata(
        conn, entity_id, main_table, primary_key_column
    )

    if force_override:
        # For force override, merge without respecting locks
        merged_metadata = _merge_metadata_force_override(current_metadata, field_value)
    else:
        merged_metadata = _merge_metadata_with_locks(current_metadata, field_value)

    logger.debug(f"Final merged metadata keys: {list(merged_metadata.keys())}")

    filtered_metadata = _filter_empty_metadata_values(merged_metadata)
    return json.dumps(filtered_metadata)


async def _get_current_metadata(
    conn: asyncpg.Connection,
    entity_id: int,
    main_table: str,
    primary_key_column: str,
) -> dict[str, Any]:
    """Get current metadata from the database."""
    current_metadata_query = (
        f"SELECT metadata FROM {main_table} WHERE {primary_key_column} = $1"
    )
    current_metadata_result = await conn.fetchval(current_metadata_query, entity_id)

    if not current_metadata_result:
        return {}

    if isinstance(current_metadata_result, str):
        result = json.loads(current_metadata_result)
        return result  # type: ignore[no-any-return]
    elif isinstance(current_metadata_result, dict):
        return current_metadata_result

    return {}


def _merge_metadata_with_locks(
    current_metadata: dict[str, Any], new_metadata: dict[str, Any]
) -> dict[str, Any]:
    """Merge new metadata with current metadata, respecting locked fields."""
    merged_metadata = current_metadata.copy()

    # First, preserve all existing lock fields
    _preserve_existing_lock_fields(current_metadata, merged_metadata)

    # Process each field in the update data
    for key, value in new_metadata.items():
        if _is_lock_field(key):
            _handle_lock_field_update(key, value, merged_metadata)
        else:
            _handle_regular_field_update(key, value, current_metadata, merged_metadata)

    # Handle explicit unlock operations
    _handle_explicit_unlocks(new_metadata, merged_metadata)

    return merged_metadata


def _preserve_existing_lock_fields(
    current_metadata: dict[str, Any], merged_metadata: dict[str, Any]
) -> None:
    """Preserve all existing lock fields in merged metadata."""
    for existing_key, existing_value in current_metadata.items():
        if _is_lock_field(existing_key):
            merged_metadata[existing_key] = existing_value
            logger.debug(
                f"Preserving existing lock field: {existing_key} = {existing_value}"
            )


def _is_lock_field(key: str) -> bool:
    """Check if a key represents a lock field."""
    return key.startswith("__") and key.endswith("__lock__")


def _handle_lock_field_update(
    key: str, value: Any, merged_metadata: dict[str, Any]
) -> None:
    """Handle update of a lock field."""
    if value is None:
        # Remove the lock field
        merged_metadata.pop(key, None)
        logger.debug(f"Removing lock field: {key}")
    else:
        merged_metadata[key] = value
        logger.debug(f"Updating lock field: {key} = {value}")


def _handle_regular_field_update(
    key: str,
    value: Any,
    current_metadata: dict[str, Any],
    merged_metadata: dict[str, Any],
) -> None:
    """Handle update of a regular (non-lock) field."""
    lock_field_name = f"__{key}__lock__"
    is_locked = current_metadata.get(lock_field_name, False)

    if not is_locked:
        # Field is not locked, allow update
        merged_metadata[key] = value
        logger.debug(f"Updating unlocked field: {key}")
    else:
        logger.debug(f"Skipping locked field: {key}")


def _handle_explicit_unlocks(
    new_metadata: dict[str, Any], merged_metadata: dict[str, Any]
) -> None:
    """Handle explicit unlock operations."""
    for key, value in new_metadata.items():
        if _is_lock_field(key) and value is None:
            # This was an explicit unlock operation
            merged_metadata.pop(key, None)
            logger.debug(f"Explicit unlock - removing field: {key}")


def _merge_metadata_force_override(
    current_metadata: dict[str, Any], new_metadata: dict[str, Any]
) -> dict[str, Any]:
    """Merge metadata with force override - ignore all lock constraints."""
    merged_metadata = current_metadata.copy()

    # Apply all updates from new_metadata, ignoring lock status
    for key, value in new_metadata.items():
        merged_metadata[key] = value
        logger.debug(f"Force override - updating field: {key}")

    return merged_metadata


async def _execute_update_query(
    conn: asyncpg.Connection,
    update_fields: list[str],
    values: list[str | int],
    entity_id: int,
    primary_key_column: str,
    main_table: str,
) -> None:
    """Execute the update query."""
    query_values: list[Any]

    if (
        not update_fields or len(update_fields) == 1
    ):  # Only updated_at was updated (no actual changes)
        query = f"""
            UPDATE {main_table}
            SET updated_at = NOW()
            WHERE {primary_key_column} = $1
        """
        query_values = [entity_id]
    else:
        # Build the complete update query
        update_clause = ", ".join(update_fields)
        query = f"""
            UPDATE {main_table}
            SET {update_clause}
            WHERE {primary_key_column} = ${len(values) + 1}
        """
        query_values = values + [entity_id]

    try:
        await conn.execute(query, *query_values)
        logger.info(f"Successfully updated entity {entity_id}")
    except asyncpg.UniqueViolationError as e:
        if "name" in str(e):
            raise ValueError("An entity with the name already exists")
        raise ValueError(f"Update failed due to constraint violation: {e}")
    except asyncpg.ForeignKeyViolationError as e:
        raise ValueError(f"Update failed due to invalid reference: {e}")


async def _resolve_entity_for_override(
    conn: asyncpg.Connection,
    entity_data: dict[str, Any],
    main_table: str,
    primary_key_column: str,
) -> dict[str, Any] | None:
    """
    Resolve entity ID and UUID for override operation.

    Returns dict with entity_id and entity_uuid, or None if not resolvable.
    """
    # Case 1: UUID provided directly
    if "uuid" in entity_data:
        entity_uuid = entity_data["uuid"]
        query = f"SELECT {primary_key_column}, uuid FROM {main_table} WHERE uuid = $1"
        result = await conn.fetchrow(query, entity_uuid)

        if result:
            return {
                "entity_id": result[primary_key_column],
                "entity_uuid": result["uuid"],
            }
        else:
            logger.warning(f"Entity with UUID {entity_uuid} not found")
            return None

    # Case 2: Compute UUID from available properties
    try:
        # Get the navigation table info to compute UUID
        schema_discovery = await get_schema_discovery(conn)
        navigation_analysis = await schema_discovery.analyze_navigation_structure(
            main_table
        )

        # Extract foreign key values for UUID computation
        foreign_key_ids = {}
        entity_name = entity_data.get("name")

        if not entity_name:
            logger.warning("Cannot compute UUID: 'name' field is required")
            return None

        # Map entity data to foreign key IDs
        for entity_key, nav_info in navigation_analysis["navigation_tables"].items():
            # entity_key is like "category", "type", etc.
            # nav_info contains "table_name", "foreign_key_column", etc.

            if entity_key in entity_data:
                table_name = nav_info["table_name"]
                primary_key_col = nav_info.get("primary_key", "id")  # Default to 'id'
                foreign_key_col = nav_info["foreign_key_column"]

                # Look up the ID for this entity
                lookup_query = (
                    f"SELECT {primary_key_col} FROM {table_name} WHERE name = $1"
                )
                lookup_result = await conn.fetchrow(
                    lookup_query, entity_data[entity_key]
                )

                if lookup_result:
                    foreign_key_ids[foreign_key_col] = lookup_result[primary_key_col]
                else:
                    logger.warning(
                        f"Cannot find {entity_key} with name '{entity_data[entity_key]}'"
                    )
                    return None

        # Generate UUID using the same logic as entity creation
        computed_uuid = str(generate_entity_uuid(entity_name, **foreign_key_ids))

        # Look up entity by computed UUID
        query = f"SELECT {primary_key_column}, uuid FROM {main_table} WHERE uuid = $1"
        result = await conn.fetchrow(query, computed_uuid)

        if result:
            return {
                "entity_id": result[primary_key_column],
                "entity_uuid": result["uuid"],
            }
        else:
            logger.warning(f"Entity with computed UUID {computed_uuid} not found")
            return None

    except Exception as e:
        logger.error(f"Error computing UUID for entity {entity_data}: {e}")
        return None


async def _resolve_entity_by_uuid_only(
    conn: asyncpg.Connection,
    entity_uuid: str,
    main_table: str,
    primary_key_column: str,
) -> dict[str, Any] | None:
    """
    Resolve entity ID and UUID by UUID only (no computation).

    Returns dict with entity_id and entity_uuid, or None if not found.
    """
    query = f"SELECT {primary_key_column}, uuid FROM {main_table} WHERE uuid = $1"
    result = await conn.fetchrow(query, entity_uuid)

    if result:
        return {
            "entity_id": result[primary_key_column],
            "entity_uuid": result["uuid"],
        }
    else:
        logger.warning(f"Entity with UUID {entity_uuid} not found")
        return None


async def _get_entity_with_metadata(
    conn: asyncpg.Connection,
    entity_id: int,
    main_table: str,
    primary_key_column: str,
) -> dict[str, Any] | None:
    """Get entity with full metadata for lock checking."""
    query = f"""
        SELECT * FROM {main_table}
        WHERE {primary_key_column} = $1
    """
    result = await conn.fetchrow(query, entity_id)

    if result:
        return dict(result)
    return None


def _filter_empty_metadata_values(metadata: dict[str, Any]) -> dict[str, Any]:
    """Filter out keys with empty string values, null values, and empty lists from metadata."""
    return {k: v for k, v in metadata.items() if v != "" and v is not None and v != []}


async def _get_main_table_primary_key(conn: asyncpg.Connection, main_table: str) -> str:
    """Get the primary key column name for the main table."""
    query = """
        SELECT column_name
        FROM information_schema.key_column_usage kcu
        JOIN information_schema.table_constraints tc
            ON kcu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
        AND kcu.table_name = $1
        AND kcu.table_schema = 'public'
        ORDER BY kcu.ordinal_position
        LIMIT 1
    """
    result = await conn.fetchval(query, main_table)
    if not result:
        # Fallback to convention-based naming
        table_singular = main_table.rstrip("s")
        return f"{table_singular}_id"
    return str(result)
