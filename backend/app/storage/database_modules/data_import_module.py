"""
Data import functionality for the Database class.

This module handles JSON data import operations with entity processing,
navigation entity creation, and metadata management.
"""

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import asyncpg

from app.models.generic import GenericEntityCreate
from app.storage.database_modules.entity_management_module import (
    get_valid_table_columns,
)
from app.storage.json_data_model import (
    BaseEntityCollection,
    BaseEntityData,
    EntityTypeRegistry,
)
from app.storage.schema_discovery import get_schema_discovery
from app.utils.logging_utils import get_logger
from app.utils.parsing_utils import process_entity_data_for_dates, try_parse_value_auto
from app.utils.uuid_utils import generate_entity_uuid

if TYPE_CHECKING:
    from app.storage.database import Database

logger = get_logger()


# NOTE: This function can be changed by users
async def import_data(database: "Database", json_content: bytes) -> None:
    """Parses JSON content and upserts the data into the database with proper transaction handling."""
    try:
        collection = _parse_json_content(json_content)
    except ValueError as e:
        # If the file format is incompatible, log and skip without raising an error
        if "skipping incompatible format" in str(e):
            logger.warning(f"Skipping JSON file with incompatible format: {e}")
            return
        else:
            # Re-raise other validation errors
            logger.error(f"Unexpected validation error: {e}")
            raise

    main_table = database.config["application"]["main_table"]

    # Process each entity in its own transaction to avoid transaction abort issues
    (
        processed_count,
        failed_count,
    ) = await _process_entity_collection_with_recovery(database, collection, main_table)

    _log_import_results(processed_count, failed_count)
    _validate_import_success(processed_count, failed_count)

    logger.info("Import operation completed successfully")


# Helper functions for data import


def _parse_json_content(json_content: bytes) -> BaseEntityCollection:
    """Parse and validate JSON content using registered collection classes."""
    try:
        # Try to decode bytes to string with robust encoding detection
        try:
            # First try UTF-8 (most common)
            content_str = json_content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                # Try UTF-8 with error handling
                content_str = json_content.decode("utf-8", errors="replace")
                logger.warning(
                    "File contains invalid UTF-8 characters, replaced with placeholders"
                )
            except UnicodeDecodeError:
                try:
                    # Try Latin-1 as fallback (can decode any byte sequence)
                    content_str = json_content.decode("latin-1")
                    logger.warning("File decoded using Latin-1 encoding as fallback")
                except UnicodeDecodeError as e:
                    logger.warning(
                        f"Failed to decode file with multiple encodings: {e}"
                    )
                    raise ValueError(
                        f"Unable to decode file content - skipping incompatible format: {e}"
                    ) from e

        # Parse the decoded string as JSON
        raw_data = json.loads(content_str)

        # Check if this JSON has the expected structure
        if not isinstance(raw_data, dict):
            raise ValueError(
                "JSON root must be an object - skipping incompatible format"
            )

        # Use registry to detect the appropriate collection class
        collection_class = EntityTypeRegistry.detect_collection_class(raw_data)
        if not collection_class:
            raise ValueError(
                "No suitable collection class found for this JSON structure - skipping incompatible format"
            )

        return collection_class.model_validate(raw_data)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON format in file: {e}")
        raise ValueError(
            f"Invalid JSON format - skipping incompatible format: {e}"
        ) from e
    except ValueError:
        # Re-raise ValueError as-is (includes our "skipping incompatible format" cases)
        raise
    except Exception as e:
        # For Pydantic validation errors and other exceptions, mark as incompatible format
        logger.warning(f"Data validation failed for file: {e}")
        raise ValueError(
            f"Data validation failed - skipping incompatible format: {e}"
        ) from e


async def _process_entity_collection_with_recovery(
    database: "Database", collection: BaseEntityCollection, main_table: str
) -> tuple[int, int]:
    """Process all entity in the collection using batch transactions with fallback."""
    batch_size = database.config["application"]["batch_size"]

    total_processed = 0
    total_failed = 0

    # Split entities into batches
    entities = collection.get_entities()

    for batch_start in range(0, len(entities), batch_size):
        batch_end = min(batch_start + batch_size, len(entities))
        batch = entities[batch_start:batch_end]
        batch_indices = list(range(batch_start, batch_end))

        logger.info(
            f"Processing batch {batch_start // batch_size + 1}: entities {batch_start + 1}-{batch_end} of {len(entities)}"
        )

        # Try batch processing first (all-or-nothing)
        batch_processed, batch_failed = await _process_batch_all_or_nothing(
            database, batch, batch_indices, main_table
        )

        # If batch failed, fall back to individual processing
        if batch_failed > 0 and batch_processed == 0:
            logger.warning(
                f"Batch failed, falling back to individual processing for batch {batch_start // batch_size + 1}"
            )
            batch_processed, batch_failed = await _process_batch_individually(
                database, batch, batch_indices, main_table
            )

        total_processed += batch_processed
        total_failed += batch_failed

        logger.info(
            f"Batch {batch_start // batch_size + 1} completed: {batch_processed} processed, {batch_failed} failed"
        )

    return total_processed, total_failed


async def _process_batch_all_or_nothing(
    database: "Database",
    batch: list[BaseEntityData],
    batch_indices: list[int],
    main_table: str,
) -> tuple[int, int]:
    """Process a batch of entities in a single transaction (all-or-nothing)."""
    try:
        async with database.session() as conn:
            async with conn.transaction():
                # Get navigation structure once for the entire batch
                navigation_structure = await _get_navigation_entity_structure(
                    database, conn
                )

                # Pre-populate navigation entities for the entire batch
                navigation_cache = await _preprocess_batch_navigation_entities(
                    database, conn, batch
                )

                # Process all entities in the batch
                for idx, entity_data in zip(batch_indices, batch, strict=True):
                    await _process_single_entity(
                        conn,
                        entity_data,
                        idx,
                        main_table,
                        navigation_cache,
                        navigation_structure,
                        database,
                    )

                # If we get here, all entities succeeded
                return len(batch), 0

    except Exception as e:
        logger.error(f"Batch transaction failed: {e}")
        # Return 0 processed, all failed - will trigger individual fallback
        return 0, len(batch)


async def _process_batch_individually(
    database: "Database",
    batch: list[BaseEntityData],
    batch_indices: list[int],
    main_table: str,
) -> tuple[int, int]:
    """Process batch entities individually (fallback when batch fails)."""
    processed_count = 0
    failed_count = 0

    for idx, entity_data in zip(batch_indices, batch, strict=True):
        # Process each entity in its own session and transaction
        try:
            async with database.session() as conn:
                async with conn.transaction():
                    # Get navigation structure and create cache for this single entity
                    navigation_structure = await _get_navigation_entity_structure(
                        database, conn
                    )

                    # Create navigation cache for just this entity
                    navigation_cache = await _preprocess_batch_navigation_entities(
                        database, conn, [entity_data]
                    )

                    await _process_single_entity(
                        conn,
                        entity_data,
                        idx,
                        main_table,
                        navigation_cache,
                        navigation_structure,
                        database,
                    )
                    processed_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to process entity at index {idx}: {e}")
            # Continue processing other entities instead of aborting

    return processed_count, failed_count


async def _preprocess_batch_navigation_entities(
    database: "Database", conn: asyncpg.Connection, batch: list[BaseEntityData]
) -> dict[str, dict[str, int]]:
    """Pre-populate all navigation entities for a batch and return ID cache."""
    # Get dynamic navigation structure from config and schema
    entity_structure = await _get_navigation_entity_structure(database, conn)

    if not entity_structure:
        return {}

    # Collect all unique navigation entity names from the batch
    unique_entities: dict[str, set[str]] = {}

    for entity_data in batch:
        for entity_key, entity_info in entity_structure.items():
            field_name = entity_info["field_name"]

            # Get entity name from direct JSON field
            entity_name: str | None = None
            if hasattr(entity_data, field_name):
                field_value = getattr(entity_data, field_name)
                if field_value and str(field_value).strip():
                    entity_name = str(field_value).strip()

            if entity_name:
                if entity_key not in unique_entities:
                    unique_entities[entity_key] = set()
                unique_entities[entity_key].add(entity_name)

    # Create all navigation entities and build cache
    navigation_cache: dict[str, dict[str, int]] = {}

    for entity_key, names in unique_entities.items():
        entity_info = entity_structure[entity_key]
        table_name = entity_info["table_name"]
        navigation_cache[entity_key] = {}

        for name in names:
            # Create the entity and cache its ID
            entity_id = await _get_or_create_entity(
                conn,
                GenericEntityCreate,
                table_name,
                name=name,
            )
            navigation_cache[entity_key][name] = entity_id

    return navigation_cache


async def _process_single_entity(
    conn: asyncpg.Connection,
    entity_data: BaseEntityData,
    idx: int,
    main_table: str,
    navigation_cache: dict[str, dict[str, int]],
    navigation_structure: dict[str, dict[str, str]],
    database: "Database",
) -> None:
    """Process a single entity using pre-populated navigation entity cache."""
    entity_name = _generate_entity_name(entity_data, idx, database)
    logger.info(f"Processing: {entity_name}")

    # Get foreign key IDs from cache instead of creating individually
    foreign_key_ids = await _get_foreign_key_ids_from_cache(
        entity_data, navigation_cache, navigation_structure
    )

    # Get metadata and create the main entity
    metadata_dict = entity_data.get_all_metadata()
    await _create_main_entity_with_conflict_resolution(
        conn, entity_name, metadata_dict, foreign_key_ids, main_table, database
    )


async def _get_foreign_key_ids_from_cache(
    entity_data: BaseEntityData,
    navigation_cache: dict[str, dict[str, int]],
    navigation_structure: dict[str, dict[str, str]],
) -> dict[str, int | None]:
    """Get foreign key IDs from the navigation cache using dynamic navigation structure.

    Args:
        entity_data: The entity data containing field values
        navigation_cache: Pre-populated cache of navigation entities
        navigation_structure: Dynamic structure mapping entity keys to foreign key columns

    Returns:
        Dictionary mapping foreign key column names to their IDs
    """
    foreign_key_ids: dict[str, int | None] = {}

    # Use dynamic navigation structure instead of hardcoded mappings
    for entity_key, entity_info in navigation_structure.items():
        foreign_key_col = entity_info["foreign_key_column"]

        if entity_key in navigation_cache:
            # Try to find the entity name for this entity
            entity_name = _get_name_for_entity(entity_data, entity_key)

            if entity_name and entity_name in navigation_cache[entity_key]:
                foreign_key_ids[foreign_key_col] = navigation_cache[entity_key][
                    entity_name
                ]
            else:
                foreign_key_ids[foreign_key_col] = None
        else:
            foreign_key_ids[foreign_key_col] = None

    return foreign_key_ids


def _get_name_for_entity(entity_data: BaseEntityData, field_name: str) -> str | None:
    """Get the entity name for a specific entity key from entity data."""
    if not field_name:
        return None

    # Get entity name from direct JSON field
    entity_name = None
    if hasattr(entity_data, field_name):
        field_value = getattr(entity_data, field_name)
        if field_value and str(field_value).strip():
            entity_name = str(field_value).strip()

    return entity_name


def _generate_entity_name(
    entity_data: BaseEntityData, idx: int, database: "Database"
) -> str:
    """Generate entity name with fallback if the configured entity name field is missing."""
    # Get the configured entity name field from config
    entity_name_field = database.config["application"].get("entity_name_field", "name")

    # Try to get the name from the configured field, then fallback to standard fields
    entity_name = getattr(entity_data, entity_name_field, None) or getattr(
        entity_data, "name", None
    )
    if not entity_name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        entity_name = f"unnamed_entity_{timestamp}_{short_uuid}_{idx}"
        logger.warning(
            f"Entity at index {idx} has no '{entity_name_field}' nor 'name' field. Using fallback name: {entity_name}"
        )
    return entity_name


async def _get_navigation_entity_structure(
    database: "Database", conn: asyncpg.Connection
) -> dict[str, dict[str, str]]:
    """Get dynamic navigation entity structure from config and schema."""
    try:
        main_table = database.config["application"]["main_table"]
        navigation_order = database.config["navigation"]["order"]

        # Use schema discovery to get the actual table mappings
        schema_discovery = await get_schema_discovery(conn)
        navigation_analysis = await schema_discovery.analyze_navigation_structure(
            main_table
        )

        # Build entity structure mapping: entity_key -> {table_name, field_name}
        entity_structure = {}
        for entity_key in navigation_order:
            # Skip empty or whitespace-only entity keys
            if not entity_key or not entity_key.strip():
                logger.warning(f"Skipping empty navigation entity key: '{entity_key}'")
                continue

            # Clean the entity key
            entity_key = entity_key.strip()

            # Default to conventional plural table name
            table_name = f"{entity_key}s"

            # Try to find actual table name from schema analysis
            if entity_key in navigation_analysis["navigation_tables"]:
                table_name = navigation_analysis["navigation_tables"][entity_key][
                    "table_name"
                ]

            # Field name matches the entity key (e.g., "accelerator", "file_type")
            field_name = entity_key

            entity_structure[entity_key] = {
                "table_name": table_name,
                "field_name": field_name,
                "foreign_key_column": f"{entity_key}_id",
            }

        return entity_structure

    except Exception as e:
        logger.error(f"Failed to get dynamic navigation structure: {e}")
        try:
            navigation_order = database.config["navigation"]["order"]

            # Build minimal structure from config only
            entity_structure = {}
            for entity_key in navigation_order:
                # Use conventional naming patterns
                table_name = f"{entity_key}s"
                field_name = entity_key

                entity_structure[entity_key] = {
                    "table_name": table_name,
                    "field_name": field_name,
                    "foreign_key_column": f"{entity_key}_id",
                }

            logger.info(
                f"Using config-only navigation structure with {len(entity_structure)} entities"
            )
            return entity_structure

        except Exception as config_error:
            logger.error(
                f"Failed to build navigation structure from config: {config_error}"
            )
            # If even config fails, return empty structure - let the calling code handle gracefully
            return {}


async def _create_main_entity_with_conflict_resolution(
    conn: asyncpg.Connection,
    entity_name: str,
    metadata_dict: dict[str, Any],
    foreign_key_ids: dict[str, int | None],
    main_table: str,
    database: "Database",
) -> None:
    """Create main entity using UUID-based conflict resolution."""
    try:
        await _create_main_entity(
            conn, entity_name, metadata_dict, foreign_key_ids, main_table, database
        )
    except Exception as e:
        # Log any errors but don't do name-based retries since UUID handles uniqueness
        logger.error(f"Failed to create/update entity for {entity_name}: {e}")
        raise


async def _create_main_entity(
    conn: asyncpg.Connection,
    name: str,
    metadata_dict: dict[str, Any],
    foreign_key_ids: dict[str, int | None],
    main_table: str,
    database: "Database",
) -> None:
    """Create the main entity in the database."""
    # Generate deterministic UUID based on key fields
    entity_uuid = generate_entity_uuid(
        entity_name=name,
        **foreign_key_ids,
    )

    # Create entity dictionary dynamically
    entity_dict: dict[str, Any] = {
        "name": name,
        "metadata": metadata_dict,
    }

    # Generic metadata processing with automatic date/timestamp parsing
    # Extract title from metadata if available, fallback to name
    title = metadata_dict.get("title", name) if metadata_dict else name
    entity_dict["title"] = title

    # Extract other direct database fields from metadata if available
    if metadata_dict:
        logger.debug(f"Processing metadata for {name}: {list(metadata_dict.keys())}")

        valid_columns = await get_valid_table_columns(conn, main_table)

        # Get the configured entity name field from config
        entity_name_field = database.config["application"].get(
            "entity_name_field", "name"
        )

        # Exclude system columns that shouldn't be set directly
        system_columns = {
            "uuid",
            "created_at",
            "updated_at",
            "last_edited_at",
            "edited_by_name",
            "metadata",
            "title",
            entity_name_field,  # Dynamic based on config (default: "name")
        }

        # Get metadata fields that correspond to actual database columns
        direct_fields = valid_columns - system_columns

        # Filter to only include fields that exist in metadata
        available_direct_fields = [
            field for field in direct_fields if field in metadata_dict
        ]

        for field in available_direct_fields:
            value = metadata_dict[field]

            # Use generic parsing for all fields
            parsed_value = try_parse_value_auto(value)

            # Special handling for authors - ensure it's a list and not empty
            if field == "authors":
                logger.debug(
                    f"Processing authors field for {name}: {parsed_value} (type: {type(parsed_value)})"
                )
                if isinstance(parsed_value, list) and len(parsed_value) > 0:
                    entity_dict[field] = parsed_value
                    logger.debug(f"Set authors to: {parsed_value}")
                elif isinstance(parsed_value, str) and parsed_value.strip():
                    # Convert single author string to array
                    entity_dict[field] = [parsed_value.strip()]
                    logger.debug(
                        f"Converted single author string to array: {[parsed_value.strip()]}"
                    )
                else:
                    logger.warning(
                        f"Invalid or empty authors field: {parsed_value}, using fallback"
                    )
                    entity_dict[field] = ["Unknown Author"]
                continue

            # For all other fields, use the parsed value directly
            entity_dict[field] = parsed_value

        # Ensure required fields are present with fallbacks
        if "authors" not in entity_dict or not entity_dict["authors"]:
            logger.warning(f"No authors found for {name}, using fallback")
            entity_dict["authors"] = ["Unknown Author"]

    # Add all foreign key IDs dynamically
    entity_dict.update(foreign_key_ids)
    # Add the UUID to the entity dictionary
    entity_dict["uuid"] = entity_uuid

    entity_dict = await _merge_metadata_with_locked_fields(
        conn, entity_dict, main_table
    )

    # Process metadata for date/timestamp fields after merging with locked fields
    if "metadata" in entity_dict and entity_dict["metadata"]:
        entity_dict["metadata"] = process_entity_data_for_dates(entity_dict["metadata"])

    # Build and execute the upsert query
    await _upsert_entity(conn, entity_dict, main_table)


async def _merge_metadata_with_locked_fields(
    conn: asyncpg.Connection, entity_dict: dict[str, Any], main_table: str
) -> dict[str, Any]:
    """Merge new metadata with existing locked fields."""
    if "metadata" not in entity_dict or entity_dict["metadata"] is None:
        return entity_dict

    new_metadata = entity_dict["metadata"]
    existing_metadata_result = await conn.fetchval(
        f"SELECT metadata FROM {main_table} WHERE uuid = $1",
        entity_dict["uuid"],
    )

    if existing_metadata_result:
        existing_metadata = _parse_existing_metadata(existing_metadata_result)
        merged_metadata = _merge_metadata_respecting_locks(
            existing_metadata, new_metadata
        )
        filtered_metadata = _filter_empty_metadata_values(merged_metadata)
        entity_dict["metadata"] = json.dumps(filtered_metadata)
    else:
        # New entity, use new metadata as-is (filtered)
        filtered_metadata = _filter_empty_metadata_values(new_metadata)
        entity_dict["metadata"] = json.dumps(filtered_metadata)

    return entity_dict


def _parse_existing_metadata(metadata_result: Any) -> dict[str, Any]:
    """Parse existing metadata from database result."""
    if isinstance(metadata_result, str):
        result = json.loads(metadata_result)
        return result  # type: ignore[no-any-return]
    elif isinstance(metadata_result, dict):
        return metadata_result
    return {}


def _filter_empty_metadata_values(metadata: dict[str, Any]) -> dict[str, Any]:
    """Filter out keys with empty string values, null values, and empty lists from metadata."""
    return {k: v for k, v in metadata.items() if v != "" and v is not None and v != []}


def _merge_metadata_respecting_locks(
    existing_metadata: dict[str, Any], new_metadata: dict[str, Any]
) -> dict[str, Any]:
    """Merge metadata while respecting locked fields."""
    merged_metadata = existing_metadata.copy()

    for key, value in new_metadata.items():
        # For lock field updates, allow them to pass through
        if key.startswith("__") and key.endswith("__lock__"):
            merged_metadata[key] = value
            continue

        # Check if this field is locked
        lock_field_name = f"__{key}__lock__"
        is_locked = existing_metadata.get(lock_field_name, False)

        if not is_locked:
            # Field is not locked, allow update
            merged_metadata[key] = value
        # If field is locked, keep the existing value

    return merged_metadata


async def _upsert_entity(
    conn: asyncpg.Connection,
    entity_dict: dict[str, Any],
    main_table: str,
    user_info: dict[str, Any] | None = None,
) -> None:
    """Execute the upsert query for the main entity, respecting locked fields."""
    columns = list(entity_dict.keys())
    placeholders = [f"${i + 1}" for i in range(len(columns))]
    values = list(entity_dict.values())

    # Build the conflict update clause with SQL-based lock checking
    update_clauses = []
    updateable_fields = []  # Track fields that can be updated (for last_edited_at logic)

    for col in columns:
        if col != "uuid":  # Don't update the conflict column
            # Generate SQL-based lock check for this field
            lock_check_sql = (
                f"COALESCE(({main_table}.metadata->'__{col}__lock__')::boolean, false)"
            )

            # Use CASE statement to conditionally update based on lock status
            case_sql = f"""
                {col} = CASE
                    WHEN {lock_check_sql} THEN {main_table}.{col}
                    ELSE EXCLUDED.{col}
                END"""

            update_clauses.append(case_sql)
            updateable_fields.append(col)

    # Always update updated_at for any operation
    update_clauses.append("updated_at = NOW()")

    # Handle last_edited_at and edited_by_name for manual operations
    if user_info:
        # For manual operations, update last_edited_at if any unlocked fields could be updated
        # We check if at least one field is unlocked using SQL logic
        unlocked_conditions = []
        for col in updateable_fields:
            lock_check_sql = (
                f"COALESCE(({main_table}.metadata->'__{col}__lock__')::boolean, false)"
            )
            unlocked_conditions.append(f"NOT {lock_check_sql}")

        if unlocked_conditions:
            # Update last_edited_at if any field is unlocked (meaning manual changes are possible)
            any_unlocked_sql = " OR ".join(unlocked_conditions)
            update_clauses.append(f"""
                last_edited_at = CASE
                    WHEN ({any_unlocked_sql}) THEN NOW()
                    ELSE {main_table}.last_edited_at
                END""")

            # Update edited_by_name if user info is provided and any field is unlocked
            if "name" in user_info:
                user_name_escaped = user_info["name"].replace(
                    "'", "''"
                )  # Escape single quotes
                update_clauses.append(f"""
                    edited_by_name = CASE
                        WHEN ({any_unlocked_sql}) THEN '{user_name_escaped}'
                        ELSE {main_table}.edited_by_name
                    END""")

    # Clean up the update clauses (remove extra whitespace and newlines)
    cleaned_clauses = [
        clause.strip().replace("\n", " ").replace("  ", " ")
        for clause in update_clauses
    ]

    query = f"""
        INSERT INTO {main_table} ({", ".join(columns)})
        VALUES ({", ".join(placeholders)})
        ON CONFLICT (uuid) DO UPDATE
        SET {", ".join(cleaned_clauses)}
    """

    await conn.execute(query, *values)


def _log_import_results(processed_count: int, failed_count: int) -> None:
    """Log the results of the import operation."""
    if failed_count > 0:
        logger.warning(
            f"Import completed with {failed_count} failures out of {processed_count + failed_count} total entities"
        )
    else:
        logger.info(f"Successfully processed all {processed_count} entities")


def _validate_import_success(processed_count: int, failed_count: int) -> None:
    """Validate that the import was successful enough to continue."""
    total_entities = processed_count + failed_count
    if total_entities > 0 and failed_count > (total_entities / 2):
        raise RuntimeError(
            f"Import failed: {failed_count}/{total_entities} entities could not be processed"
        )


async def _get_or_create_entity(
    conn: asyncpg.Connection, model: type, table_name: str, **kwargs: Any
) -> int:
    """Generic function to get an entity by name or create it within a transaction."""
    name = kwargs.get("name")
    if not name:
        raise ValueError("A 'name' is required to find or create an entity.")

    id_column = f"{table_name.rstrip('s')}_id"
    query = f"SELECT {id_column} FROM {table_name} WHERE name ILIKE $1"

    record = await conn.fetchrow(query, name)
    if record:
        return int(record[id_column])

    instance = model(**kwargs)
    data = instance.model_dump(exclude_unset=True)
    columns = ", ".join(data.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(data)))

    insert_query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) RETURNING {id_column}"

    try:
        new_id = await conn.fetchval(insert_query, *data.values())
        if new_id is None:
            raise RuntimeError(
                f"Failed to create entity in {table_name} with name {name}"
            )
        return int(new_id)
    except asyncpg.UniqueViolationError:
        # Handle race condition where another transaction created the entity
        record = await conn.fetchrow(query, name)
        if record:
            return int(record[id_column])
        raise RuntimeError(
            f"Failed to create or find entity in {table_name} with name {name}"
        )
