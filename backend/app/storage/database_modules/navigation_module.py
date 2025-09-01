"""
Navigation functionality for the Database class.

This module handles navigation-related operations like dropdown items
and sorting field discovery based on database schema analysis.
"""

from typing import TYPE_CHECKING, Any

import asyncpg

if TYPE_CHECKING:
    from app.storage.database import Database
from app.utils.logging_utils import get_logger

logger = get_logger()


async def get_sorting_fields(
    database: "Database",
) -> dict[str, Any]:
    """
    Dynamically fetch available sorting fields from the database schema.
    Returns categorized lists of sortable fields based on the current database structure.
    """
    main_table = database.config["application"]["main_table"]

    async with database.session() as conn:
        schema_data = await _fetch_schema_data(conn, main_table)
        field_collections = _build_field_collections(schema_data)
        all_fields = _combine_and_sort_fields(field_collections)

    return {
        "fields": all_fields,
        "count": len(all_fields),
        "info": "All available fields for sorting. Metadata fields can be used with or without 'metadata.' prefix (e.g., 'status' or 'metadata.status').",
    }


async def get_dropdown_items(
    database: "Database",
    table_key: str,
    main_table: str,
    navigation_analysis: dict[str, Any],
    filter_dict: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Get dropdown items for any navigation table based on schema discovery.
    Returns only items that have related entities.
    """
    if filter_dict is None:
        filter_dict = {}

    async with database.session() as conn:
        if table_key not in navigation_analysis["navigation_tables"]:
            raise ValueError(f"Navigation table '{table_key}' not found")

        table_info = navigation_analysis["navigation_tables"][table_key]
        base_query = _build_dropdown_base_query(table_info, table_key, main_table)

        conditions, params = await _process_dropdown_filters(
            conn, filter_dict, navigation_analysis
        )

        final_query = _finalize_dropdown_query(
            base_query, conditions, table_info["name_column"]
        )
        rows = await conn.fetch(final_query, *params)

        items = [{"id": row["id"], "name": row["name"]} for row in rows]
        return {"data": items}


# Helper functions for navigation operations


async def _fetch_schema_data(
    conn: asyncpg.Connection, main_table: str
) -> dict[str, Any]:
    """Fetch all schema-related data needed for sorting fields."""
    try:
        entity_columns = await _fetch_entity_columns(conn, main_table)
        foreign_keys = await _fetch_foreign_keys(conn, main_table)
        metadata_keys = await _fetch_metadata_keys(conn, main_table)
        nested_metadata_keys = await _fetch_nested_metadata_keys(conn, main_table)

        return {
            "entity_columns": entity_columns,
            "foreign_keys": foreign_keys,
            "metadata_keys": metadata_keys,
            "nested_metadata_keys": nested_metadata_keys,
        }
    except Exception as e:
        logger.error(f"Failed to execute schema discovery queries: {e}")
        raise


async def _fetch_entity_columns(
    conn: asyncpg.Connection, main_table: str
) -> list[dict[str, Any]]:
    """Fetch entity column information."""
    result = await conn.fetch(f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = '{main_table}'
        AND table_schema = 'public'
        ORDER BY ordinal_position
    """)
    return list(result)


async def _fetch_foreign_keys(
    conn: asyncpg.Connection, main_table: str
) -> list[dict[str, Any]]:
    """Fetch foreign key information."""
    result = await conn.fetch(f"""
        SELECT
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_name = '{main_table}'
        AND tc.table_schema = 'public'
    """)
    return list(result)


async def _fetch_metadata_keys(
    conn: asyncpg.Connection, main_table: str
) -> list[dict[str, Any]]:
    """Fetch metadata field keys, excluding lock fields."""
    result = await conn.fetch(f"""
        WITH metadata_keys AS (
            SELECT DISTINCT jsonb_object_keys(metadata) as metadata_key
            FROM {main_table}
            WHERE metadata IS NOT NULL
            AND metadata != 'null'::jsonb
        )
        SELECT metadata_key
        FROM metadata_keys
        WHERE metadata_key NOT LIKE '__%__lock__'
        ORDER BY metadata_key
    """)
    return list(result)


async def _fetch_nested_metadata_keys(
    conn: asyncpg.Connection, main_table: str
) -> list[dict[str, Any]]:
    """Fetch nested metadata field keys, excluding lock fields."""
    result = await conn.fetch(f"""
        WITH nested_keys AS (
            SELECT DISTINCT
                parent_key || '.' || child_key as nested_key
            FROM (
                SELECT
                    parent_key,
                    jsonb_object_keys(parent_value) as child_key
                FROM (
                    SELECT
                        key as parent_key,
                        value as parent_value
                    FROM {main_table}, jsonb_each(metadata)
                    WHERE metadata IS NOT NULL
                    AND metadata != 'null'::jsonb
                    AND jsonb_typeof(value) = 'object'
                ) nested_objects
            ) expanded_keys
        )
        SELECT nested_key
        FROM nested_keys
        WHERE nested_key NOT LIKE '__%__lock__%'
        AND nested_key NOT LIKE '%__lock__'
        ORDER BY nested_key
    """)
    return list(result)


def _build_field_collections(schema_data: dict[str, Any]) -> dict[str, list[str]]:
    """Build different field collections from schema data."""
    entity_fields = _build_entity_fields(
        schema_data["entity_columns"], schema_data["foreign_keys"]
    )
    joined_fields = _build_joined_fields(schema_data["foreign_keys"])
    metadata_fields = _build_metadata_fields(schema_data["metadata_keys"])
    nested_fields = _build_nested_fields(schema_data["nested_metadata_keys"])

    return {
        "entity_fields": entity_fields,
        "joined_fields": joined_fields,
        "metadata_fields": metadata_fields,
        "nested_fields": nested_fields,
    }


def _build_entity_fields(
    entity_columns: list[dict[str, Any]], foreign_keys: list[dict[str, Any]]
) -> list[str]:
    """Build entity fields excluding foreign keys and metadata."""
    foreign_key_columns = {fk["column_name"] for fk in foreign_keys}
    entity_fields = []

    for col in entity_columns:
        col_name = col["column_name"]
        if col_name not in foreign_key_columns and col_name != "metadata":
            entity_fields.append(col_name)

    return entity_fields


def _build_joined_fields(foreign_keys: list[dict[str, Any]]) -> list[str]:
    """Build joined fields from foreign key relationships."""
    joined_fields = []
    for fk in foreign_keys:
        fk_column = fk["column_name"]
        # Convert foreign key column name to corresponding joined field name
        # e.g., accelerator_id -> accelerator_name
        if fk_column.endswith("_id"):
            base_name = fk_column[:-3]  # Remove '_id' suffix
            joined_field_name = f"{base_name}_name"
            joined_fields.append(joined_field_name)

    return joined_fields


def _build_metadata_fields(metadata_keys: list[dict[str, Any]]) -> list[str]:
    """Build metadata fields list, filtering out lock fields."""
    metadata_fields = []
    for row in metadata_keys:
        key = row["metadata_key"]
        # Double-check to exclude lock fields (in case SQL filter missed any)
        if not (key.startswith("__") and key.endswith("__lock__")):
            # Only add the prefixed version to avoid duplicates
            metadata_fields.append(
                f"metadata.{key}"
            )  # Prefixed access (e.g., "metadata.cross-section")
    return metadata_fields


def _build_nested_fields(nested_metadata_keys: list[dict[str, Any]]) -> list[str]:
    """Build nested metadata fields list, filtering out lock fields."""
    nested_fields = []
    for row in nested_metadata_keys:
        key = row["nested_key"]
        # Double-check to exclude lock fields (in case SQL filter missed any)
        if "__lock__" not in key:
            # Only add the prefixed version to avoid duplicates
            nested_fields.append(
                f"metadata.{key}"
            )  # Prefixed access (e.g., "metadata.process.name")
    return nested_fields


def _combine_and_sort_fields(field_collections: dict[str, list[str]]) -> list[str]:
    """Combine all field collections and sort alphabetically."""
    all_fields = []
    all_fields.extend(field_collections["entity_fields"])
    all_fields.extend(field_collections["joined_fields"])
    all_fields.extend(field_collections["metadata_fields"])
    all_fields.extend(field_collections["nested_fields"])

    # Sort alphabetically for better UX
    all_fields.sort()
    return all_fields


def _build_dropdown_base_query(
    table_info: dict[str, Any], table_key: str, main_table: str
) -> str:
    """Build the base query for dropdown items."""
    table_name = table_info["table_name"]
    primary_key = table_info["primary_key"]
    name_column = table_info["name_column"]

    return f"""
        SELECT DISTINCT t.{primary_key} as id, t.{name_column} as name
        FROM {table_name} t
        INNER JOIN {main_table} d ON d.{table_key}_id = t.{primary_key}
    """


async def _process_dropdown_filters(
    conn: asyncpg.Connection,
    filter_dict: dict[str, str],
    navigation_analysis: dict[str, Any],
) -> tuple[list[str], list[Any]]:
    """Process filter conditions for dropdown queries."""
    conditions: list[str] = []
    params: list[Any] = []

    for filter_key, filter_value in filter_dict.items():
        if filter_key.endswith("_name"):
            condition, param = await _process_name_filter(
                conn, filter_key, filter_value, navigation_analysis
            )
            if condition and param is not None:
                conditions.append(condition.replace("$PARAM", f"${len(params) + 1}"))
                params.append(param)
        elif filter_key.endswith("_id"):
            conditions.append(f"d.{filter_key} = ${len(params) + 1}")
            params.append(filter_value)

    return conditions, params


async def _process_name_filter(
    conn: asyncpg.Connection,
    filter_key: str,
    filter_value: str,
    navigation_analysis: dict[str, Any],
) -> tuple[str | None, int | None]:
    """Process a name-based filter, converting it to an ID filter."""
    entity_key = filter_key.replace("_name", "")

    if entity_key not in navigation_analysis["navigation_tables"]:
        return None, None

    filter_table_info = navigation_analysis["navigation_tables"][entity_key]
    filter_table_name = filter_table_info["table_name"]
    filter_name_column = filter_table_info["name_column"]
    filter_pk = filter_table_info["primary_key"]

    # Get the ID for this filter value (case-insensitive)
    id_result = await conn.fetchval(
        f"SELECT {filter_pk} FROM {filter_table_name} WHERE {filter_name_column} ILIKE $1",
        filter_value,
    )

    if id_result:
        return f"d.{entity_key}_id = $PARAM", id_result

    return None, None


def _finalize_dropdown_query(
    base_query: str, conditions: list[str], name_column: str
) -> str:
    """Add WHERE clause and ORDER BY to the dropdown query."""
    query = base_query

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += f" ORDER BY t.{name_column}"
    return query
