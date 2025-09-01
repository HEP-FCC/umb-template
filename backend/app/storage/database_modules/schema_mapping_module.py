"""
Schema mapping functionality for the Database class.

This module handles dynamic schema discovery and mapping generation
for the query parser based on database structure.
"""

from typing import TYPE_CHECKING, Any

import asyncpg

if TYPE_CHECKING:
    from app.storage.database import Database

from app.storage.schema_discovery import get_schema_discovery
from app.utils.logging_utils import get_logger
from app.utils.sql_utils import generate_unique_table_alias

logger = get_logger()


async def generate_schema_mapping(
    database: "Database",
) -> dict[str, str]:
    """
    Generates a dynamic schema mapping for the query parser based on database schema.

    This method analyzes the database structure and creates mappings for:
    - Entity fields: entity_id, name, created_at, last_edited_at
    - Dynamic joined fields: {entity}_name for each navigation entity
    - Metadata fields: metadata.* (any key in the JSONB metadata field)
    """
    logger.info("Generating dynamic schema mapping for query parser.")

    try:
        main_table = database.config["application"]["main_table"]

        async with database.session() as conn:
            primary_key_column = await _get_main_table_primary_key(conn, main_table)
            base_mapping = await _create_base_mapping(
                conn, main_table, primary_key_column
            )
            navigation_mapping = await _create_navigation_mapping(conn, main_table)

            # Combine both mappings
            return {**base_mapping, **navigation_mapping}

    except Exception as e:
        logger.error(f"Failed to generate dynamic schema mapping: {e}")
        # Return base mapping on failure
        return {
            "entity_id": "d.entity_id",  # Fallback primary key
            "name": "d.name",
            "uuid": "d.uuid",
            "metadata": "d.metadata",
            "metadata_text": "jsonb_values_to_text(d.metadata)",
            "created_at": "d.created_at",
            "updated_at": "d.updated_at",
            "last_edited_at": "d.last_edited_at",
            "edited_by_name": "d.edited_by_name",
        }


async def _create_base_mapping(
    conn: asyncpg.Connection, main_table: str, primary_key_column: str
) -> dict[str, str]:
    """Create base field mappings dynamically from the database schema."""
    try:
        # Get all columns from the main table
        valid_columns = await _get_valid_table_columns(conn, main_table)

        base_mapping = {}

        # Add all table columns dynamically
        for column_name in valid_columns:
            base_mapping[column_name] = f"d.{column_name}"

        # Add special computed fields
        if "metadata" in valid_columns:
            base_mapping["metadata_text"] = "jsonb_values_to_text(d.metadata)"

        logger.debug(
            f"Generated dynamic base mapping with {len(base_mapping)} fields: {list(base_mapping.keys())}"
        )
        return base_mapping

    except Exception as e:
        logger.warning(
            f"Failed to create dynamic base mapping, falling back to hardcoded mapping: {e}"
        )
        # Fallback to the original hardcoded mapping
        return {
            "name": "d.name",
            "uuid": "d.uuid",
            "metadata": "d.metadata",
            "metadata_text": "jsonb_values_to_text(d.metadata)",
            primary_key_column: f"d.{primary_key_column}",
            "created_at": "d.created_at",
            "updated_at": "d.updated_at",
            "last_edited_at": "d.last_edited_at",
            "edited_by_name": "d.edited_by_name",
        }


async def _create_navigation_mapping(
    conn: asyncpg.Connection, main_table: str
) -> dict[str, str]:
    """Create navigation entity mappings based on schema discovery."""
    try:
        schema_discovery = await get_schema_discovery(conn)
        navigation_analysis = await schema_discovery.analyze_navigation_structure(
            main_table
        )

        return _build_navigation_aliases(navigation_analysis["navigation_tables"])

    except Exception as e:
        logger.warning(f"Failed to create navigation mapping: {e}")
        return {}


def _build_navigation_aliases(navigation_tables: dict[str, Any]) -> dict[str, str]:
    """Build alias mappings for navigation entities."""
    mapping = {}
    used_aliases = {"d"}  # 'd' is reserved for the main table

    for entity_key, table_info in navigation_tables.items():
        name_column = table_info["name_column"]
        alias = generate_unique_table_alias(entity_key, used_aliases)
        used_aliases.add(alias)
        mapping[entity_key] = f"{alias}.{name_column}"

    return mapping


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


async def _get_valid_table_columns(
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
