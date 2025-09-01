"""
Entity retrieval functionality for the Database class.

This module handles fetching entities by ID with full details
and related navigation entity information.
"""

import json
from typing import TYPE_CHECKING, Any

import asyncpg

if TYPE_CHECKING:
    from app.storage.database import Database

from app.storage.schema_discovery import get_schema_discovery
from app.utils.logging_utils import get_logger
from app.utils.sql_utils import generate_unique_table_alias

logger = get_logger()


async def get_entities_by_ids(
    database: "Database", entity_ids: list[int]
) -> list[dict[str, Any]]:
    """
    Get entities by their IDs with all details and related entity names.
    Returns a list of dictionaries with all entity fields plus metadata flattened to top-level.
    """
    if not entity_ids:
        return []

    main_table = database.config["application"]["main_table"]

    # Build dynamic query with navigation tables
    try:
        async with database.session() as conn:
            # Get the primary key column dynamically
            primary_key_column = await _get_main_table_primary_key(conn, main_table)

            schema_discovery = await get_schema_discovery(conn)
            navigation_analysis = await schema_discovery.analyze_navigation_structure(
                main_table
            )

            # Build SELECT fields dynamically
            select_fields = [
                f"d.{primary_key_column}",
                "d.uuid",
                "d.name",
                "d.metadata",
                "d.created_at",
                "d.updated_at",
                "d.last_edited_at",
            ]

            # Build JOIN clauses dynamically
            joins = [f"FROM {main_table} d"]
            used_aliases = {"d"}

            for entity_key, table_info in navigation_analysis[
                "navigation_tables"
            ].items():
                table_name = table_info["table_name"]
                primary_key = table_info["primary_key"]
                name_column = table_info["name_column"]

                # Generate unique alias
                alias = generate_unique_table_alias(entity_key, used_aliases)
                used_aliases.add(alias)

                # Add foreign key field to SELECT
                select_fields.append(f"d.{entity_key}_id")

                # Add name field to SELECT
                select_fields.append(f"{alias}.{name_column} as {entity_key}_name")

                # Add JOIN clause
                joins.append(
                    f"LEFT JOIN {table_name} {alias} ON d.{entity_key}_id = {alias}.{primary_key}"
                )

            query = f"""
                SELECT {", ".join(select_fields)}
                {" ".join(joins)}
                WHERE d.{primary_key_column} = ANY($1)
                ORDER BY d.{primary_key_column}
            """

    except Exception as e:
        logger.error(f"Failed to build dynamic query: {e}")
        # Fallback to simpler query without navigation joins
        # We still need to get the primary key for the fallback
        async with database.session() as conn:
            primary_key_column = await _get_main_table_primary_key(conn, main_table)

        query = f"""
            SELECT d.*
            FROM {main_table} d
            WHERE d.{primary_key_column} = ANY($1)
            ORDER BY d.{primary_key_column}
        """

    async with database.session() as conn:
        records = await conn.fetch(query, entity_ids)

        result = []
        for record in records:
            # Convert record to dict
            entity_dict = dict(record)

            # Extract and flatten metadata
            metadata_str = entity_dict.pop("metadata", r"{}")
            metadata = json.loads(metadata_str)

            # Merge metadata keys into the main dictionary
            # If there's a conflict, the original entity fields take precedence
            for key, value in metadata.items():
                if key not in entity_dict:
                    entity_dict[key] = value

            result.append(entity_dict)

        return result


async def get_entity_by_id(
    database: "Database", entity_id: int
) -> dict[str, Any] | None:
    """
    Get a single entity by ID with all details and related entity names.
    Returns None if entity is not found.
    """
    entities = await get_entities_by_ids(database, [entity_id])
    return entities[0] if entities else None


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
