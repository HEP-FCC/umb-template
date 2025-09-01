"""
SQL utilities for database operations.

This module provides common SQL utility functions that are used across
multiple database modules to avoid code duplication.
"""

from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def generate_unique_table_alias(entity_key: str, used_aliases: set[str]) -> str:
    """
    Generate a unique alias for a table, avoiding conflicts and SQL reserved keywords.

    This function creates safe, unique table aliases for SQL queries by:
    1. Starting with a short prefix based on the entity key
    2. Avoiding SQL reserved keywords
    3. Ensuring uniqueness among already used aliases
    4. Adding numeric suffixes when needed to resolve conflicts

    Args:
        entity_key: The entity key to create an alias for (e.g., "category", "publication_type")
        used_aliases: Set of already used aliases to avoid conflicts

    Returns:
        A unique, safe table alias string

    Example:
        >>> generate_unique_table_alias("category", set())
        "cat"
        >>> generate_unique_table_alias("from", set())  # "from" is reserved
        "f_t"
        >>> generate_unique_table_alias("category", {"cat"})
        "cat1"
    """
    # SQL reserved keywords to avoid
    reserved_keywords = {
        "for",
        "from",
        "where",
        "select",
        "update",
        "delete",
        "insert",
        "join",
        "on",
        "as",
        "in",
        "or",
        "and",
        "not",
        "if",
        "order",
        "by",
        "group",
        "having",
        "union",
        "all",
        "exists",
        "case",
        "when",
        "then",
        "else",
        "end",
        "distinct",
        "limit",
        "offset",
        "into",
        "values",
        "set",
        "create",
        "drop",
        "alter",
        "table",
        "index",
        "view",
        "trigger",
        "procedure",
        "function",
        "schema",
        "database",
        "constraint",
        "primary",
        "foreign",
        "key",
        "unique",
        "null",
        "default",
        "check",
        "references",
    }

    # Start with first 3-4 characters if entity key is long enough
    if len(entity_key) > 3:
        base_alias = entity_key[:3]
    else:
        base_alias = entity_key

    # If it's a reserved keyword, try first 4 characters
    if base_alias.lower() in reserved_keywords and len(entity_key) > 3:
        base_alias = entity_key[:4]

    # If still a reserved keyword, use first character + suffix
    if base_alias.lower() in reserved_keywords:
        base_alias = entity_key[0] + "_t"  # Add "_t" suffix for "table"

    # If already used, try first 4 characters (if not already tried)
    if base_alias in used_aliases and len(entity_key) > 3 and len(base_alias) < 4:
        base_alias = entity_key[:4]

    # If still conflicts, add number suffix
    if base_alias in used_aliases:
        counter = 1
        original_alias = base_alias
        while f"{original_alias}{counter}" in used_aliases:
            counter += 1
        base_alias = f"{original_alias}{counter}"

    return base_alias


def build_safe_column_name(column_name: str) -> str:
    """
    Build a safe column name by quoting it if necessary.

    This function ensures column names are safe to use in SQL queries
    by adding quotes when the column name contains special characters
    or matches SQL reserved keywords.

    Args:
        column_name: The column name to make safe

    Returns:
        A safe column name, quoted if necessary
    """
    # Simple validation - if column contains spaces or special chars, quote it
    if any(char in column_name for char in [" ", "-", ".", ":", ";", "(", ")"]):
        return f'"{column_name}"'

    # Check if it's a reserved keyword (case-insensitive)
    reserved_keywords = {
        "order",
        "by",
        "group",
        "having",
        "where",
        "select",
        "from",
        "join",
        "on",
        "as",
        "in",
        "or",
        "and",
        "not",
        "case",
        "when",
        "then",
        "else",
        "end",
        "distinct",
        "limit",
        "offset",
        "union",
        "all",
        "exists",
    }

    if column_name.lower() in reserved_keywords:
        return f'"{column_name}"'

    return column_name


def escape_sql_identifier(identifier: str) -> str:
    """
    Escape a SQL identifier (table name, column name, etc.) for safe use in queries.

    Args:
        identifier: The SQL identifier to escape

    Returns:
        Escaped identifier safe for use in SQL queries
    """
    # Replace any quotes with double quotes and wrap in quotes
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def build_where_clause_with_params(
    conditions: list[str], logical_operator: str = "AND"
) -> str:
    """
    Build a WHERE clause from a list of conditions.

    Args:
        conditions: List of condition strings
        logical_operator: Operator to join conditions ("AND" or "OR")

    Returns:
        Complete WHERE clause string, or empty string if no conditions
    """
    if not conditions:
        return ""

    if len(conditions) == 1:
        return f"WHERE {conditions[0]}"

    joined_conditions = f" {logical_operator} ".join(conditions)
    return f"WHERE {joined_conditions}"


def build_order_by_clause(
    sort_columns: list[str], sort_directions: list[str] | None = None
) -> str:
    """
    Build an ORDER BY clause from columns and directions.

    Args:
        sort_columns: List of column names to sort by
        sort_directions: List of directions ("ASC" or "DESC"), defaults to "ASC"

    Returns:
        Complete ORDER BY clause string, or empty string if no columns
    """
    if not sort_columns:
        return ""

    if sort_directions is None:
        sort_directions = ["ASC"] * len(sort_columns)

    # Ensure we have a direction for each column
    while len(sort_directions) < len(sort_columns):
        sort_directions.append("ASC")

    order_parts = []
    for i, column in enumerate(sort_columns):
        direction = sort_directions[i].upper()
        if direction not in ("ASC", "DESC"):
            direction = "ASC"
        order_parts.append(f"{build_safe_column_name(column)} {direction}")

    return f"ORDER BY {', '.join(order_parts)}"
