"""
Search operations functionality for the Database class.

This module handles search queries, entity searches, and related
database query operations with dynamic schema support.
"""

import json
import re
from typing import TYPE_CHECKING, Any

import asyncpg

if TYPE_CHECKING:
    from app.storage.database import Database

from app.utils.errors_utils import SearchValidationError
from app.utils.logging_utils import get_logger
from app.utils.sql_utils import generate_unique_table_alias

logger = get_logger()


async def perform_search(
    database: "Database",
    count_query: str,
    search_query: str,
    params: list[Any],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    async with database.session() as conn:
        try:
            total_records_result = await conn.fetchval(count_query, *params)
            total_records = total_records_result or 0

            records = await conn.fetch(
                f"{search_query} LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
                *params,
                limit,
                offset,
            )

        except asyncpg.UndefinedColumnError as e:
            logger.warning(
                f"Column not found in database schema: {e}. Attempting fallback to metadata search..."
            )

            # Extract the missing column name from the error message
            error_msg = str(e)

            column_match = re.search(r'column "([^"]+)" does not exist', error_msg)
            if column_match:
                missing_column = column_match.group(1)
                logger.info(f"Missing column identified: {missing_column}")

                # Check if this is a direct field access (d.field_name) - if so, it's an invalid field
                if (
                    f"d.{missing_column}" in search_query
                    or f"d.{missing_column}" in count_query
                ):
                    # This means user tried to search by a field that doesn't exist
                    raise SearchValidationError(
                        message=f"Field '{missing_column}' does not exist in the database schema",
                        error_type="invalid_field",
                        field_name=missing_column,
                        user_message=f"The field '{missing_column}' is not available for searching. Please check the field name and try again.",
                    )

                # Replace the column reference with metadata access in both queries
                fallback_count_query = count_query.replace(
                    f"d.{missing_column}", f"d.metadata->>'{missing_column}'"
                )
                fallback_search_query = search_query.replace(
                    f"d.{missing_column}", f"d.metadata->>'{missing_column}'"
                )

                logger.info(
                    f"Retrying with fallback queries using metadata access for column: {missing_column}"
                )

                try:
                    # Retry with fallback queries
                    total_records_result = await conn.fetchval(
                        fallback_count_query, *params
                    )
                    total_records = total_records_result or 0

                    records = await conn.fetch(
                        f"{fallback_search_query} LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
                        *params,
                        limit,
                        offset,
                    )

                    logger.info(
                        f"Fallback query successful for missing column: {missing_column}"
                    )
                except Exception as fallback_error:
                    logger.error(f"Fallback query also failed: {fallback_error}")
                    # If fallback also fails, raise a more informative error
                    raise SearchValidationError(
                        message=f"Field '{missing_column}' does not exist in database schema or metadata",
                        error_type="invalid_field",
                        field_name=missing_column,
                        user_message=f"The field '{missing_column}' is not available for searching. Please check the field name and try again.",
                    )
            else:
                logger.error(f"Could not extract column name from error: {error_msg}")
                # Generic undefined column error
                raise SearchValidationError(
                    message=f"Database column error: {error_msg}",
                    error_type="invalid_field",
                    user_message="One or more fields in your search query are not available. Please check your field names and try again.",
                )

        except Exception as e:
            logger.error(f"Failed to execute search queries: {e}")
            raise

        # Convert records to dictionaries and parse JSON metadata
        items = []
        for record in records:
            item_dict = dict(record)

            # Parse metadata JSON string to object if it exists
            if "metadata" in item_dict and item_dict["metadata"]:
                try:
                    item_dict["metadata"] = json.loads(item_dict["metadata"])
                except (json.JSONDecodeError, TypeError):
                    # If parsing fails, keep as string or set to empty dict
                    item_dict["metadata"] = {}
            else:
                item_dict["metadata"] = {}

            items.append(item_dict)

        return {"total": total_records, "items": items}


async def search_entities(
    database: "Database",
    main_table: str,
    navigation_analysis: dict[str, Any],
    filters: dict[str, str] | None = None,
    search: str = "",
    page: int = 1,
    limit: int = 25,
) -> dict[str, Any]:
    """
    Generic search endpoint that works with any database schema.
    Automatically handles joins based on schema discovery.
    """
    if filters is None:
        filters = {}

    async with database.session() as conn:
        query_parts, join_parts, entity_aliases = _build_search_query_parts(
            navigation_analysis
        )
        conditions, params = _build_search_conditions(
            navigation_analysis, filters, search, entity_aliases
        )

        base_query = _assemble_base_query(
            query_parts,
            join_parts,
            conditions,
            navigation_analysis["main_table_schema"]["primary_key"],
        )
        count_query = _build_count_query(base_query, query_parts, main_table)

        # Execute queries and return results
        total = await conn.fetchval(count_query, *params) or 0

        offset = (page - 1) * limit
        paginated_query = (
            f"{base_query} LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        )
        rows = await conn.fetch(paginated_query, *params, limit, offset)

        items = [dict(row) for row in rows]
        return {"total": total, "items": items}


# Import the consolidated utility function


def _build_search_query_parts(
    navigation_analysis: dict[str, Any],
) -> tuple[list[str], list[str], dict[str, str]]:
    """Build SELECT columns and JOIN clauses for navigation entities."""
    query_parts = []
    join_parts = []
    used_aliases: set[str] = set()
    entity_aliases = {}  # Map entity_key -> table_alias

    for entity in navigation_analysis["navigation_entities"]:
        entity_key = entity["key"]
        table_alias = generate_unique_table_alias(entity_key, used_aliases)
        used_aliases.add(table_alias)
        entity_aliases[entity_key] = table_alias

        referenced_table = entity["referenced_table"]
        column_name = entity["column_name"]
        name_column = navigation_analysis["navigation_tables"][entity_key][
            "name_column"
        ]
        primary_key = navigation_analysis["navigation_tables"][entity_key][
            "primary_key"
        ]

        query_parts.append(f", {table_alias}.{name_column} as {entity_key}_name")
        join_parts.append(
            f"LEFT JOIN {referenced_table} {table_alias} ON d.{column_name} = {table_alias}.{primary_key}"
        )

    return query_parts, join_parts, entity_aliases


def _build_search_conditions(
    navigation_analysis: dict[str, Any],
    filters: dict[str, str],
    search: str,
    entity_aliases: dict[str, str],
) -> tuple[list[str], list[Any]]:
    """Build WHERE conditions and parameters for the search query."""
    conditions: list[str] = []
    params: list[Any] = []

    # Add filter conditions
    _add_filter_conditions(
        navigation_analysis, filters, conditions, params, entity_aliases
    )

    # Add search conditions
    if search:
        _add_search_conditions(navigation_analysis, search, conditions, params)

    return conditions, params


def _add_filter_conditions(
    navigation_analysis: dict[str, Any],
    filters: dict[str, str],
    conditions: list[str],
    params: list[Any],
    entity_aliases: dict[str, str],
) -> None:
    """Add filter conditions to the query."""
    for filter_key, filter_value in filters.items():
        if filter_key.endswith("_name"):
            entity_key = filter_key.replace("_name", "")
            if entity_key in navigation_analysis["navigation_tables"]:
                table_alias = entity_aliases.get(
                    entity_key, entity_key[0]
                )  # Fallback to first character
                name_column = navigation_analysis["navigation_tables"][entity_key][
                    "name_column"
                ]
                conditions.append(f"{table_alias}.{name_column} = ${len(params) + 1}")
                params.append(filter_value)


def _add_search_conditions(
    navigation_analysis: dict[str, Any],
    search: str,
    conditions: list[str],
    params: list[Any],
) -> None:
    """Add text search conditions to the query."""
    search_conditions = []

    for col in navigation_analysis["main_table_schema"]["columns"]:
        if any(
            text_type in col["data_type"].lower()
            for text_type in ["text", "varchar", "character"]
        ):
            search_conditions.append(f"d.{col['column_name']} ILIKE ${len(params) + 1}")

    if search_conditions:
        search_condition = "(" + " OR ".join(search_conditions) + ")"
        conditions.append(search_condition)
        params.append(f"%{search}%")


def _assemble_base_query(
    query_parts: list[str],
    join_parts: list[str],
    conditions: list[str],
    primary_key: str,
) -> str:
    """Assemble the complete base query with WHERE and ORDER BY clauses."""
    query = "".join(query_parts)
    query += "".join(join_parts)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += f" ORDER BY d.{primary_key} DESC"
    return query


def _build_count_query(base_query: str, query_parts: list[str], main_table: str) -> str:
    """Build the count query from the base query."""
    # Find the part to replace for count query
    select_part = "SELECT d.*" + "".join(
        query_parts[1 : query_parts.index(f" FROM {main_table} d")]
    )
    return base_query.replace(select_part, "SELECT COUNT(*)")
