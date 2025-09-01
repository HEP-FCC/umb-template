"""
A Python module to parse a query language and translate it into PostgreSQL queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from lark import Lark, Token, Transformer, exceptions

from app.storage.database import Database
from app.storage.schema_discovery import get_schema_discovery
from app.utils.config_utils import get_config
from app.utils.errors_utils import SearchValidationError
from app.utils.logging_utils import get_logger
from app.utils.sql_utils import generate_unique_table_alias

logger = get_logger()

# UUID regex pattern (same as in grammar)
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def is_uuid_format(value: str) -> bool:
    """
    Check if a string matches the UUID format.

    Args:
        value: The string to check

    Returns:
        True if the string matches UUID format, False otherwise
    """
    return bool(UUID_PATTERN.match(value.strip()))


QUERY_LANGUAGE_GRAMMAR = r"""
    ?start: expr
    ?expr: expr OR term | term
    ?term: term AND factor | factor
    ?factor: NOT item | item
    ?item: "(" expr ")" | comparison | global_search
    global_search: simple_value
    comparison: field OP value?
    field: IDENTIFIER ("." IDENTIFIER)*
    value: simple_value
    simple_value: QUOTED_STRING | UUID | SIGNED_NUMBER | IDENTIFIER | ASTERISK
    AND.2: "AND"
    OR.2: "OR"
    NOT.2: "NOT"
    IDENTIFIER: /[a-zA-Z_][a-zA-Z0-9_-]*/
    UUID: /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/
    ASTERISK: "*"
    OP: "=" | "!=" | ">" | "<" | ">=" | "<=" | ":" | "!:" | "=~" | "!~" | "#"
    QUOTED_STRING: /"[^"]*"/ | /'[^']*'/
    %import common.SIGNED_NUMBER
    %import common.WS
    %ignore WS
"""


def parse_date_string(date_str: str) -> datetime:
    """
    Parse a date string in various formats to a datetime object.
    Supports formats like:
    - "2025-07-20" (date only)
    - "2025-07-20 15:30:00" (date and time)
    - "2025-07-20T15:30:00" (ISO format)
    """
    # Remove quotes if present
    date_str = date_str.strip("\"'")

    # List of supported formats
    formats = [
        "%Y-%m-%d",  # "2025-07-20"
        "%Y-%m-%d %H:%M:%S",  # "2025-07-20 15:30:00"
        "%Y-%m-%dT%H:%M:%S",  # "2025-07-20T15:30:00"
        "%Y-%m-%d %H:%M",  # "2025-07-20 15:30"
        "%Y-%m-%dT%H:%M",  # "2025-07-20T15:30"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # If none of the formats work, raise an error
    raise ValueError(f"Unable to parse date string: {date_str}")


@dataclass(frozen=True)
class Field:
    parts: tuple[str, ...]

    def to_sql(
        self,
        schema_mapping: dict[str, str],
        value: Any = None,
        op: str | None = None,
        available_metadata_fields: set[str] | None = None,
        string_fields: set[str] | None = None,
        id_fields: set[str] | None = None,
        entity_fields: set[str] | None = None,
    ) -> str:
        base_field = self.parts[0]
        if base_field[-5:] == "_name":
            base_field = base_field[:-5]

        sql_column = schema_mapping.get(base_field)

        # Validate operation and value compatibility early
        self._validate_operation_compatibility(
            base_field, op, value, available_metadata_fields, string_fields, id_fields
        )

        if not sql_column:
            # Check if this might be a foreign key field (entity reference)
            # Use dynamically fetched entity fields from database schema
            entity_fields = entity_fields or set()
            if base_field in entity_fields:
                # Map to the foreign key column in the entity table
                sql_column = f"d.{base_field}_id"
            elif available_metadata_fields and base_field in available_metadata_fields:
                # AUTO-DETECT: If field doesn't exist as regular column but exists in metadata,
                # automatically treat it as metadata.{field}
                logger.debug("Auto-detecting metadata field: %s", base_field)

                # Construct metadata field access
                metadata_column = schema_mapping.get("metadata", "d.metadata")
                json_path_parts = self.parts  # Use all parts for nested access

                if len(json_path_parts) == 1:
                    # Simple metadata field: field -> metadata.field
                    json_field = f"{metadata_column}->>'{json_path_parts[0]}'"
                else:
                    # Nested metadata field: field.sub -> metadata.field.sub
                    path_expression = "->".join(
                        [f"'{part}'" for part in json_path_parts[:-1]]
                    )
                    json_field = f"{metadata_column}->{path_expression}->>'{json_path_parts[-1]}'"

                # Handle numeric casting for comparison operators
                if (
                    value is not None
                    and isinstance(value, int | float)
                    and op in ("=", "!=", ">", "<", ">=", "<=", ":")
                ):
                    json_field = f"({json_field})::numeric"

                return json_field
            else:
                # Field not found in schema or metadata - raise validation error
                available_fields = list(schema_mapping.keys())
                if available_metadata_fields:
                    available_fields.extend(list(available_metadata_fields))

                field_path = ".".join(self.parts)
                raise SearchValidationError(
                    message=f"Field '{field_path}' does not exist in the database schema or metadata",
                    error_type="invalid_field",
                    field_name=field_path,
                    user_message=f"The field '{field_path}' is not available for searching. Available fields include: {', '.join(sorted(available_fields)[:10])}{'...' if len(available_fields) > 10 else ''}",
                )

        # Handle explicit metadata fields (metadata.field syntax)
        if base_field == "metadata" and len(self.parts) > 1:
            json_path_parts = self.parts[1:]
            path_expression = "->".join([f"'{part}'" for part in json_path_parts[:-1]])

            # Determine if we need to cast based on the value type and operator
            json_field = (
                f"{sql_column}->{path_expression}->>'{json_path_parts[-1]}'"
                if len(json_path_parts) > 1
                else f"{sql_column}->>'{json_path_parts[0]}'"
            )

            # If comparing with a number and using equality/comparison operators, cast to numeric
            if (
                value is not None
                and isinstance(value, int | float)
                and op in ("=", "!=", ">", "<", ">=", "<=", ":")
            ):
                # Cast the JSON text value to numeric for comparison
                return f"({json_field})::numeric"

            return json_field
        return sql_column

    def _validate_operation_compatibility(
        self,
        field_name: str,
        op: str | None,
        value: Any,
        available_metadata_fields: set[str] | None = None,
        string_fields: set[str] | None = None,
        id_fields: set[str] | None = None,
    ) -> None:
        """Validate that the operation and value are compatible with the field type."""
        if not op or value is None:
            return

        # Use provided field classifications or empty sets as fallback
        string_fields = string_fields or set()
        id_fields = id_fields or set()

        # Check if this is a metadata field
        is_metadata_field = (
            available_metadata_fields and field_name in available_metadata_fields
        ) or field_name == "metadata"

        # Validate string fields
        if field_name in string_fields and not is_metadata_field:
            if op in (">", "<", ">=", "<=") and isinstance(value, int | float):
                raise SearchValidationError(
                    message=f"Cannot use numeric comparison operator '{op}' with string field '{field_name}'",
                    error_type="invalid_operation",
                    field_name=field_name,
                    operation=op,
                    user_message=f"The field '{field_name}' contains text values and cannot be compared using '{op}'. Use '=' for exact match, ':' for contains, or '=~' for pattern matching.",
                )

            if op in (">", "<", ">=", "<=") and isinstance(value, str):
                raise SearchValidationError(
                    message=f"String comparison operator '{op}' is not supported for field '{field_name}'",
                    error_type="invalid_operation",
                    field_name=field_name,
                    operation=op,
                    user_message=f"Cannot compare text values in '{field_name}' using '{op}'. Use '=' for exact match, ':' for contains, or '=~' for pattern matching.",
                )

        # Validate ID fields - they should only accept integers
        if field_name in id_fields or field_name.endswith("_id"):
            if not isinstance(value, int) and op in ("=", "!=", ">", "<", ">=", "<="):
                try:
                    # Try to convert to int
                    int(value)
                except (ValueError, TypeError):
                    raise SearchValidationError(
                        message=f"Field '{field_name}' expects integer values, got '{value}' ({type(value).__name__})",
                        error_type="invalid_operation",
                        field_name=field_name,
                        operation=op,
                        user_message=f"The field '{field_name}' expects numeric ID values. Please provide an integer value instead of '{value}'.",
                    )

        # Validate metadata fields have special rules
        if is_metadata_field:
            self._validate_metadata_operation(op, value, field_name)

    def _validate_metadata_operation(
        self, op: str | None, value: Any, field_name: str
    ) -> None:
        """Validate that the operation is compatible with metadata fields."""
        if not op:
            return

        # Check for string comparison operations that are not supported
        if op in ("<", ">", "<=", ">=") and isinstance(value, str):
            raise SearchValidationError(
                message=f"String comparison with operator '{op}' is not supported for metadata field '{field_name}'",
                error_type="invalid_operation",
                field_name=field_name,
                operation=op,
                user_message=f"Cannot use '{op}' to compare text values in field '{field_name}'. Use '=' for exact match, ':' for contains, or '=~' for regex patterns.",
            )


@dataclass(frozen=True)
class Comparison:
    field: Field
    op: str
    value: Any


@dataclass(frozen=True)
class GlobalSearch:
    value: str
    is_quoted: bool = False


@dataclass(frozen=True)
class And:
    left: Any
    right: Any


@dataclass(frozen=True)
class Or:
    left: Any
    right: Any


@dataclass(frozen=True)
class Not:
    term: Any


AstNode = Comparison | GlobalSearch | And | Or | Not


class AstTransformer(Transformer[Token, AstNode]):
    def expr(self, i: list[Any]) -> Or | Any:
        return Or(left=i[0], right=i[2]) if len(i) > 1 else i[0]

    def term(self, i: list[Any]) -> And | Any:
        return And(left=i[0], right=i[2]) if len(i) > 1 else i[0]

    def factor(self, i: list[Any]) -> Not | Any:
        return Not(term=i[1]) if len(i) > 1 else i[0]

    def item(self, i: list[Any]) -> Any:
        # The item is already transformed by other rules (e.g., global_search)
        return i[0]

    def comparison(self, i: list[Any]) -> Comparison:
        # Handle optional value: [field, op] or [field, op, value]
        if len(i) == 2:
            # No value provided (e.g., "last_edited_at:")
            return Comparison(field=i[0], op=str(i[1]), value=None)
        else:
            # Value provided (e.g., "last_edited_at: somevalue")
            return Comparison(field=i[0], op=str(i[1]), value=i[2])

    def global_search(self, i: list[Any]) -> GlobalSearch:
        # The value is already processed by simple_value, which is the first item in the list
        processed_value = i[0]

        # Check if the value was originally quoted (comes as a tuple from simple_value)
        if isinstance(processed_value, tuple) and processed_value[0] == "quoted":
            is_quoted = True
            value = processed_value[1]
        else:
            is_quoted = False
            value = str(processed_value)

        logger.debug(
            "global_search - processed_value: %s, is_quoted: %s, value: %s",
            processed_value,
            is_quoted,
            value,
        )

        return GlobalSearch(value=value, is_quoted=is_quoted)

    def field(self, i: list[Any]) -> Field:
        return Field(parts=tuple(p.value for p in i))

    def value(self, i: list[Any]) -> float | str | Any:
        processed = i[0]
        # Handle the quoted tuple from simple_value
        if isinstance(processed, tuple) and processed[0] == "quoted":
            return processed[1]  # Return just the value part
        return processed

    def simple_value(self, i: list[Any]) -> float | str | Any:
        v = i[0]
        if hasattr(v, "type"):
            if v.type == "QUOTED_STRING":
                # Return a tuple to preserve the information that this was quoted
                return ("quoted", v.value[1:-1])
            if v.type == "SIGNED_NUMBER":
                return float(v.value) if "." in v.value else int(v.value)
            if v.type == "IDENTIFIER":
                return str(v.value)
            if v.type == "UUID":
                return str(v.value)
            if v.type == "ASTERISK":
                return "*"
        return str(v)


class SqlTranslator:
    def __init__(self) -> None:
        self.schema_mapping: dict[str, str] = {}
        self.global_search_fields: list[str] = []  # Will be set dynamically
        self.available_metadata_fields: set[str] = set()
        self.string_fields: set[str] = set()
        self.id_fields: set[str] = set()
        self.entity_fields: set[str] = set()
        self.params: list[Any] = []
        self.param_index = 0

    def reset(
        self,
        schema_mapping: dict[str, str],
        global_search_fields: list[str] | None = None,
        available_metadata_fields: set[str] | None = None,
        string_fields: set[str] | None = None,
        id_fields: set[str] | None = None,
        entity_fields: set[str] | None = None,
    ) -> None:
        self.schema_mapping = schema_mapping
        if global_search_fields is not None:
            self.global_search_fields = global_search_fields
        if available_metadata_fields is not None:
            self.available_metadata_fields = available_metadata_fields
        if string_fields is not None:
            self.string_fields = string_fields
        if id_fields is not None:
            self.id_fields = id_fields
        if entity_fields is not None:
            self.entity_fields = entity_fields
        self.params = []
        self.param_index = 0

    def translate(self, node: AstNode) -> str:
        if isinstance(node, Comparison):
            return self._translate_comparison(node)
        if isinstance(node, GlobalSearch):
            return self._translate_global_search(node)
        if isinstance(node, Not):
            return f"NOT ({self.translate(node.term)})"
        if isinstance(node, And):
            return f"({self.translate(node.left)} AND {self.translate(node.right)})"
        if isinstance(node, Or):
            return f"({self.translate(node.left)} OR {self.translate(node.right)})"
        raise TypeError(f"Unknown AST node type: {type(node)}")

    def _translate_comparison(self, node: Comparison) -> str:
        sql_field = node.field.to_sql(
            self.schema_mapping,
            node.value,
            node.op,
            self.available_metadata_fields,
            self.string_fields,
            self.id_fields,
            self.entity_fields,
        )
        op = node.op
        value = node.value

        # Handle the special :* operator for field existence
        if op == ":" and value == "*":
            return self._translate_field_exists(node.field, sql_field)

        # Handle the special !:* operator for field non-existence
        if op == "!:" and value == "*":
            return self._translate_field_not_exists(node.field, sql_field)

        # Special handling for last_edited_at field
        is_last_edited_at = node.field.parts[
            0
        ] == "last_edited_at" or sql_field.endswith("last_edited_at")

        self.param_index += 1
        placeholder = f"${self.param_index}"

        param_value: str | datetime
        if op == ":" or op == "=":
            if op == ":":
                if is_last_edited_at and (value == "" or value is None):
                    # Special case: last_edited_at: (empty value) means "show only edited entities"
                    # Don't increment param_index or add to params since we're not using a placeholder
                    self.param_index -= (
                        1  # Decrement since we incremented above but won't use it
                    )
                    return f"{sql_field} IS NOT NULL"
                else:
                    # Substring match using ILIKE
                    sql_op, param_value = "ILIKE", f"%{value}%"
            else:
                # For string values, use case-insensitive exact match (ILIKE)
                # For numeric/date values, use exact match (=)
                if isinstance(value, str) and not is_last_edited_at:
                    sql_op, param_value = "ILIKE", value
                else:
                    sql_op, param_value = "=", value
        elif op == "=~":
            # Case-insensitive regular expression match
            sql_op, param_value = "~*", value
        elif op == "!~":
            # Case-insensitive regular expression NOT match
            sql_op, param_value = "!~*", value
        elif op == "!:":
            # NOT contains - opposite of substring match
            sql_op, param_value = "NOT_ILIKE", f"%{value}%"
        elif op == "#":
            # Fuzzy string matching using PostgreSQL similarity (0.7 threshold)
            # Only applicable to string fields
            sql_op, param_value = "SIMILARITY", value
        elif op == "!=":
            # For string values, use case-insensitive not equal (NOT ... ILIKE)
            # For numeric/date values, use exact not equal (!=)
            if isinstance(value, str) and not is_last_edited_at:
                # Use NOT (field ILIKE value) for case-insensitive inequality
                sql_op, param_value = "NOT_ILIKE", value
            else:
                sql_op, param_value = "!=", value
        else:
            # Standard comparison operators: >, <, >=, <=
            sql_op, param_value = op, value

        # Special handling for last_edited_at: parse date strings to datetime objects
        if (
            is_last_edited_at
            and isinstance(param_value, str)
            and op in ("=", "!=", ">", "<", ">=", "<=")
        ):
            try:
                param_value = parse_date_string(param_value)
            except ValueError as e:
                logger.error("Error parsing date string '%s': %s", param_value, e)
                # If parsing fails, keep as string and let PostgreSQL handle it
                pass

        self.params.append(param_value)

        # For last_edited_at comparison operations, add NULL check
        if is_last_edited_at and op in (">", "<", ">=", "<=", "!="):
            if sql_op == "NOT_ILIKE":
                return f"({sql_field} IS NOT NULL AND NOT ({sql_field} ILIKE {placeholder}))"
            elif sql_op == "SIMILARITY":
                return f"({sql_field} IS NOT NULL AND similarity({placeholder}, {sql_field}) > 0.7)"
            else:
                return (
                    f"({sql_field} IS NOT NULL AND {sql_field} {sql_op} {placeholder})"
                )
        else:
            if sql_op == "NOT_ILIKE":
                return f"NOT ({sql_field} ILIKE {placeholder})"
            elif sql_op == "SIMILARITY":
                return f"similarity({placeholder}, {sql_field}) > 0.7"
            else:
                return f"{sql_field} {sql_op} {placeholder}"

    def _translate_field_exists(self, field: Any, sql_field: str) -> str:
        """
        Translate field existence checks (:* operator) to appropriate SQL.
        For regular fields, checks if NOT NULL.
        For JSON fields, checks if the key exists in the JSON object.
        """
        # Check if this is a metadata (JSON) field (explicit or auto-detected)
        if (field.parts[0] == "metadata" and len(field.parts) > 1) or (
            field.parts[0] in self.available_metadata_fields
        ):
            # Handle auto-detected metadata fields
            if field.parts[0] in self.available_metadata_fields:
                json_path = field.parts  # field.sub becomes ["field", "sub"]
            else:
                # Handle explicit metadata.field syntax
                json_path = field.parts[
                    1:
                ]  # metadata.field.sub becomes ["field", "sub"]

            if len(json_path) == 1:
                # Simple JSON key: metadata.key or auto-detected key
                # Use JSONB ? operator to check if key exists
                self.param_index += 1
                placeholder = f"${self.param_index}"
                self.params.append(json_path[0])
                return f"d.metadata ? {placeholder}"
            else:
                # Nested JSON key: metadata.nested.key or auto-detected nested.key
                # Check if the nested path exists using JSONB path functions
                path_expression = ".".join(json_path)
                self.param_index += 1
                placeholder = f"${self.param_index}"
                self.params.append(f"$.{path_expression}")
                return f"jsonb_path_exists(d.metadata, {placeholder})"
        else:
            # For regular fields, just check if NOT NULL
            return f"{sql_field} IS NOT NULL"

    def _translate_field_not_exists(self, field: Any, sql_field: str) -> str:
        """
        Translate field non-existence checks (!:* operator) to appropriate SQL.
        For regular fields, checks if IS NULL.
        For JSON fields, checks if the key does not exist in the JSON object.
        """
        # Check if this is a metadata (JSON) field (explicit or auto-detected)
        if (field.parts[0] == "metadata" and len(field.parts) > 1) or (
            field.parts[0] in self.available_metadata_fields
        ):
            # Handle auto-detected metadata fields
            if field.parts[0] in self.available_metadata_fields:
                json_path = field.parts  # field.sub becomes ["field", "sub"]
            else:
                # Handle explicit metadata.field syntax
                json_path = field.parts[
                    1:
                ]  # metadata.field.sub becomes ["field", "sub"]

            if len(json_path) == 1:
                # Simple JSON key: metadata.key or auto-detected key
                # Use NOT (JSONB ? operator) to check if key does not exist
                self.param_index += 1
                placeholder = f"${self.param_index}"
                self.params.append(json_path[0])
                return f"NOT (d.metadata ? {placeholder})"
            else:
                # Nested JSON key: metadata.nested.key or auto-detected nested.key
                # Check if the nested path does not exist using JSONB path functions
                path_expression = ".".join(json_path)
                self.param_index += 1
                placeholder = f"${self.param_index}"
                self.params.append(f"$.{path_expression}")
                return f"NOT jsonb_path_exists(d.metadata, {placeholder})"
        else:
            # For regular fields, just check if IS NULL
            return f"{sql_field} IS NULL"

    def _translate_global_search(self, node: GlobalSearch) -> str:
        # If the search value is '*' or empty, do not filter (all values are good)
        if str(node.value).strip() in ("*", ""):
            return "TRUE"

        search_value = str(node.value).strip()
        logger.debug(
            "Global search for: '%s' (quoted: %s)", search_value, node.is_quoted
        )

        # Use the pre-configured global search fields (set during reset)
        # The QueryParser should have already optimized these fields based on the search term

        # Use the helper to build the search clause
        where_clause, placeholder = self._build_global_search_clause(
            search_value, node.is_quoted, self.global_search_fields, self.param_index
        )

        # Update parameter tracking
        if placeholder:
            self.param_index += 1
            self.params.append(search_value)

        logger.debug("Global search generated clause: %s", where_clause)
        logger.debug("Global search parameter: '%s'", search_value)
        return where_clause

    def _build_search_condition(
        self, field_name: str, placeholder: str, is_quoted: bool
    ) -> str:
        """
        Build a search condition for a given field based on whether the search term is quoted.

        Args:
            field_name: The SQL field name to search in
            placeholder: The parameter placeholder (e.g., "$1")
            is_quoted: Whether the original search term was quoted

        Returns:
            A SQL condition string for this field
        """
        # Handle UUID fields specially - cast to text for string operations
        if "uuid" in field_name.lower():
            if is_quoted:
                # For quoted strings, use regex pattern matching (case-insensitive)
                return f"{field_name}::text ~* {placeholder}"
            else:
                # For unquoted terms, use case-insensitive substring search
                return f"{field_name}::text ILIKE '%' || {placeholder} || '%'"
        else:
            # Regular field handling
            if is_quoted:
                # For quoted strings, use regex pattern matching (case-insensitive)
                return f"{field_name} ~* {placeholder}"
            else:
                # For unquoted terms, use case-insensitive substring search
                return f"{field_name} ILIKE '%' || {placeholder} || '%'"

    def _build_global_search_clause(
        self,
        search_term: str,
        is_quoted: bool,
        field_list: list[str],
        param_offset: int = 0,
    ) -> tuple[str, str]:
        """
        Build a global search clause for a given search term across specified fields.

        Args:
            search_term: The term to search for
            is_quoted: Whether the search term was originally quoted
            field_list: List of field names to search in
            param_offset: Starting parameter index offset

        Returns:
            Tuple of (WHERE clause, parameter placeholder used)
        """
        if not search_term.strip():
            return "TRUE", ""

        param_index = param_offset + 1
        placeholder = f"${param_index}"

        conditions = []
        for field_name in field_list:
            conditions.append(
                self._build_search_condition(field_name, placeholder, is_quoted)
            )

        if not conditions:
            return "TRUE", ""

        where_clause = f"({' OR '.join(conditions)})"
        return where_clause, placeholder


class QueryParser:
    def __init__(self, database: Database):
        self.database = database
        self.schema_mapping: dict[str, str] = {}
        self.available_metadata_fields: set[str] = (
            set()
        )  # Store available metadata fields
        self.parser = Lark(QUERY_LANGUAGE_GRAMMAR, start="start", parser="lalr")
        self.transformer = AstTransformer()
        self.translator = SqlTranslator()

        # Dynamic FROM and JOINs will be built during setup
        self.from_and_joins = ""
        self.navigation_analysis: dict[str, Any] = {}
        self.entity_aliases: dict[str, str] = {}  # Store entity_key -> alias mapping

        # Field type classifications for validation (populated during setup)
        self.string_fields: set[str] = set()
        self.id_fields: set[str] = set()
        self.entity_fields: set[str] = set()  # Navigation entity field names

    async def setup(self) -> None:
        self.config = get_config()

        # Execute setup tasks sequentially for better reliability
        try:
            # Get schema mapping first
            self.schema_mapping = await self.database.generate_schema_mapping()

            # Then get metadata fields
            self.available_metadata_fields = (
                await self._fetch_available_metadata_fields()
            )

            # Get field type classifications for validation
            await self._fetch_field_type_classifications()

        except Exception as e:
            logger.error(f"Failed to setup query parser: {e}")
            raise

        async with self.database.session() as conn:
            schema_discovery = await get_schema_discovery(conn)
            self.navigation_analysis = (
                await schema_discovery.analyze_navigation_structure(
                    self.config["application"]["main_table"]
                )
            )

        # Build dynamic FROM and JOIN clauses
        self._build_dynamic_joins()

    async def _fetch_available_metadata_fields(self) -> set[str]:
        """Fetch all available metadata field names from the database."""
        config = get_config()
        main_table = config["application"]["main_table"]

        try:
            # Get top-level metadata fields, excluding lock fields
            metadata_query = f"""
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
            """

            # Get nested metadata fields (one level deep), excluding lock fields
            nested_metadata_query = f"""
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
            """

            # Run both metadata queries concurrently using separate database sessions
            # We need separate sessions here because we're making independent database calls
            try:
                # Execute queries sequentially using a single session
                async with self.database.session() as conn:
                    # Get metadata keys first
                    metadata_keys = await conn.fetch(metadata_query)

                    # Then get nested keys
                    nested_keys = await conn.fetch(nested_metadata_query)

                # Combine all metadata field names, with additional filtering for lock fields
                all_fields = set()

                # Add top-level fields (with extra filtering as safeguard)
                for row in metadata_keys:
                    field_name = row["metadata_key"]
                    if not (
                        field_name.startswith("__") and field_name.endswith("__lock__")
                    ):
                        all_fields.add(field_name)

                # Add nested fields (with extra filtering as safeguard)
                for row in nested_keys:
                    field_name = row["nested_key"]
                    if "__lock__" not in field_name:
                        all_fields.add(field_name)

                logger.debug(
                    f"Found {len(all_fields)} available metadata fields: {sorted(all_fields)}"
                )
                return all_fields

            except Exception as e:
                # Handle any errors
                logger.error(
                    f"Failed to fetch metadata fields: {type(e).__name__}: {e}"
                )
                return set()

        except Exception as e:
            # Handle regular exceptions
            logger.error(f"Failed to fetch metadata fields: {e}")
            return set()

    async def _fetch_field_type_classifications(self) -> None:
        """Fetch field type classifications from the database schema for validation."""
        try:
            main_table = self.config["application"]["main_table"]

            async with self.database.session() as conn:
                schema_discovery = await get_schema_discovery(conn)
                schema = await schema_discovery.get_complete_schema()

                # Get main table schema
                main_table_info = schema["tables"].get(main_table)
                if not main_table_info:
                    raise ValueError(f"Main table '{main_table}' not found in schema")

                # Clear existing classifications
                self.string_fields = set()
                self.id_fields = set()
                self.entity_fields = set()

                # Classify fields from main table
                for column in main_table_info["columns"]:
                    column_name = column["column_name"]
                    data_type = column["data_type"].lower()

                    # Classify as string field
                    if self._is_string_type(data_type):
                        self.string_fields.add(column_name)

                    # Classify as ID field (foreign keys or columns ending with _id)
                    if column["is_foreign_key"] or column_name.endswith("_id"):
                        self.id_fields.add(column_name)

                # Get navigation analysis to classify navigation entity fields
                navigation_analysis = (
                    await schema_discovery.analyze_navigation_structure(main_table)
                )

                # Add navigation entity fields to classifications
                for entity_key, _ in navigation_analysis["navigation_tables"].items():
                    # Navigation entity names (like "accelerator", "detector") are string fields
                    self.string_fields.add(entity_key)

                    # Navigation entity name fields with "_name" suffix are also string fields
                    self.string_fields.add(f"{entity_key}_name")

                    # Add to entity_fields for foreign key mapping
                    self.entity_fields.add(entity_key)

                logger.debug(
                    f"Classified {len(self.string_fields)} string fields: {sorted(self.string_fields)}"
                )
                logger.debug(
                    f"Classified {len(self.id_fields)} ID fields: {sorted(self.id_fields)}"
                )
                logger.debug(
                    f"Classified {len(self.entity_fields)} entity fields: {sorted(self.entity_fields)}"
                )

        except Exception as e:
            logger.error(f"Failed to fetch field type classifications: {e}")
            raise

    def _is_string_type(self, data_type: str) -> bool:
        """Check if a PostgreSQL data type should be treated as a string type for validation."""
        string_types = {
            "text",
            "varchar",
            "character varying",
            "character",
            "char",
            "uuid",
            "name",  # PostgreSQL's internal name type
            "inet",
            "cidr",
            "macaddr",
            "macaddr8",  # Network address types (treated as strings)
            "xml",  # XML type (treated as string)
        }

        # Check exact matches and varchar/character with length specifiers
        if data_type in string_types:
            return True

        # Handle parameterized types like varchar(255), char(10), etc.
        for string_type in ["varchar", "character varying", "character", "char"]:
            if data_type.startswith(f"{string_type}(") or data_type.startswith(
                f"{string_type} ("
            ):
                return True

        return False

    def _build_dynamic_joins(self) -> None:
        """Build FROM and JOIN clauses dynamically based on schema analysis."""
        joins = [f"FROM {self.config['application']['main_table']} d"]
        used_aliases = {"d"}  # Track used aliases to avoid conflicts

        for entity_key, table_info in self.navigation_analysis[
            "navigation_tables"
        ].items():
            table_name = table_info["table_name"]
            primary_key = table_info["primary_key"]

            # Create unique alias from entity key
            alias = generate_unique_table_alias(entity_key, used_aliases)
            used_aliases.add(alias)
            self.entity_aliases[entity_key] = alias  # Store for later use

            join_clause = f"LEFT JOIN {table_name} {alias} ON d.{entity_key}_id = {alias}.{primary_key}"
            joins.append(" " * 12 + join_clause)

        self.from_and_joins = "\n".join(joins)

    def _build_dynamic_select_fields(self) -> str:
        """Build dynamic SELECT fields for navigation entities."""
        select_fields: list[str] = []

        # Get main table schema info
        main_table_schema = self.navigation_analysis.get("main_table_schema", {})
        main_table_columns = main_table_schema.get("columns", [])

        # Dynamically build main table fields with proper timezone handling for timestamp columns
        for column_info in main_table_columns:
            column_name = column_info.get("column_name")

            # Keep all fields as-is since the schema already stores timestamps in UTC
            # and they contain proper timezone information
            select_fields.append(f"d.{column_name}")

        for entity_key, table_info in self.navigation_analysis[
            "navigation_tables"
        ].items():
            name_column = table_info["name_column"]

            # Use the alias that was generated during join building
            alias = self.entity_aliases[entity_key]

            select_field = f"{alias}.{name_column} as {entity_key}_name"
            select_fields.append(" " * 20 + select_field)

        return ",\n".join(select_fields)

    def _build_dynamic_global_search_fields(self, search_term: str = "") -> list[str]:
        """Build dynamic global search fields for navigation entities.

        Args:
            search_term: The search term to optimize field selection for

        Returns:
            List of field names to search in
        """
        global_search_fields = [
            "d.name",  # Entity name
            "jsonb_values_to_text(d.metadata)",  # Metadata values
        ]

        # Only include UUID field if the search term looks like a UUID
        if search_term and is_uuid_format(search_term):
            global_search_fields.append("d.uuid")  # Entity UUID
            logger.debug(
                "Including UUID field in search - detected UUID format: %s", search_term
            )
        else:
            logger.debug(
                "Skipping UUID field - search term not UUID format: %s", search_term
            )

        # Add name fields from all navigation tables using their aliases
        for entity_key, table_info in self.navigation_analysis[
            "navigation_tables"
        ].items():
            name_column = table_info["name_column"]
            alias = self.entity_aliases[entity_key]
            global_search_fields.append(f"{alias}.{name_column}")

        return global_search_fields

    def _extract_search_term_from_ast(self, node: AstNode) -> str:
        """
        Extract the first global search term from an AST node for field optimization.

        Args:
            node: The AST node to extract search terms from

        Returns:
            The first global search term found, or empty string if none
        """
        if isinstance(node, GlobalSearch):
            return str(node.value).strip()
        elif isinstance(node, And | Or):
            # Check left side first, then right side
            left_term = self._extract_search_term_from_ast(node.left)
            if left_term:
                return left_term
            return self._extract_search_term_from_ast(node.right)
        elif isinstance(node, Not):
            return self._extract_search_term_from_ast(node.term)
        else:
            # For Comparison nodes or other types, no search term
            return ""

    def _build_fuzzy_search_clause(self, query_string: str) -> tuple[str, list[Any]]:
        """
        Build a search clause using substring/regex matching when parsing fails.
        Quoted strings use regex patterns, unquoted strings use substring matching.
        """
        # Clean up the query string - remove quotes and operators, keep the actual search content

        # Extract quoted strings first (these are likely the actual search terms)
        quoted_strings = re.findall(r'["\']([^"\']+)["\']', query_string)

        if quoted_strings:
            # If we have quoted strings, use the first one as the search term
            search_term = quoted_strings[0].strip()
            is_quoted = True
        else:
            # If no quoted strings, clean up the query by removing operators
            cleaned = re.sub(
                r"\b(AND|OR|NOT)\b", " ", query_string, flags=re.IGNORECASE
            )
            cleaned = re.sub(
                r'\w+\s*=\s*["\'][^"\']*["\']', " ", cleaned
            )  # Remove field=value pairs
            cleaned = re.sub(r"\s+", " ", cleaned).strip()  # Normalize whitespace
            search_term = cleaned if cleaned else query_string.strip()
            is_quoted = False

        logger.debug("Search extracted term: '%s' (quoted: %s)", search_term, is_quoted)

        # Build the field list for search using dynamic field selection
        field_list = self._build_dynamic_global_search_fields(search_term)

        # Use the centralized helper to build the search clause
        where_clause, _ = self.translator._build_global_search_clause(
            search_term, is_quoted, field_list, 0
        )
        params = [search_term] if search_term.strip() else []

        return where_clause, params

    def _build_hybrid_search_clause(self, query_string: str) -> tuple[str, list[Any]]:
        """
        Build a hybrid search clause that combines exact matches for valid parts
        with substring/regex search for the parts that failed to parse.
        """

        logger.debug("Building hybrid search for: '%s'", query_string)

        # Split the query into parts separated by AND
        parts = re.split(r"\s+AND\s+", query_string, flags=re.IGNORECASE)

        valid_clauses = []
        fuzzy_search_terms = []
        all_params = []

        # Extract search terms early for field optimization
        all_search_terms = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            try:
                # Try to parse this individual part
                ast = cast(AstNode, self.transformer.transform(self.parser.parse(part)))
            except exceptions.LarkError:
                # If this part fails, it's likely a search term
                all_search_terms.append(part)

        # Determine the primary search term for field optimization
        primary_search_term = ""
        if all_search_terms:
            # Use the first search term or extract from quoted strings
            quoted_strings = re.findall(
                r'["\']([^"\']+)["\']', " ".join(all_search_terms)
            )
            if quoted_strings:
                primary_search_term = quoted_strings[0].strip()
            else:
                # Clean up the first search term
                cleaned = re.sub(
                    r"\b(AND|OR|NOT)\b", " ", all_search_terms[0], flags=re.IGNORECASE
                )
                cleaned = re.sub(r'\w+\s*=\s*["\'][^"\']*["\']', " ", cleaned)
                primary_search_term = re.sub(r"\s+", " ", cleaned).strip()

        global_search_fields = self._build_dynamic_global_search_fields(
            primary_search_term
        )
        self.translator.reset(
            self.schema_mapping,
            global_search_fields,
            self.available_metadata_fields,
            self.string_fields,
            self.id_fields,
            self.entity_fields,
        )

        for part in parts:
            part = part.strip()
            if not part:
                continue

            try:
                # Try to parse this individual part
                ast = cast(AstNode, self.transformer.transform(self.parser.parse(part)))

                # If successful, translate to SQL
                clause = self.translator.translate(ast)
                valid_clauses.append(clause)

            except exceptions.LarkError:
                # If this part fails, add it to search terms
                logger.debug("Failed to parse part: '%s', adding to search", part)
                fuzzy_search_terms.append(part)

        # Collect parameters from valid clauses
        all_params.extend(self.translator.params)
        param_index = len(all_params)

        # Build search clause for failed parts
        if fuzzy_search_terms:
            # Combine all search terms into one search phrase
            fuzzy_phrase = " ".join(fuzzy_search_terms).strip()
            logger.debug("Search phrase: '%s'", fuzzy_phrase)

            # Check if the original query had quoted strings
            quoted_strings = re.findall(r'["\']([^"\']+)["\']', query_string)
            is_quoted = len(quoted_strings) > 0

            # Use the centralized helper to build the search clause
            fuzzy_clause, _ = self.translator._build_global_search_clause(
                fuzzy_phrase, is_quoted, global_search_fields, param_index
            )
            all_params.append(fuzzy_phrase)

            if fuzzy_clause != "TRUE":
                valid_clauses.append(fuzzy_clause)
                logger.debug("Added search clause: %s", fuzzy_clause)

        # Combine all clauses with AND
        if valid_clauses:
            where_clause = f"({' AND '.join(valid_clauses)})"
        else:
            where_clause = "TRUE"

        return where_clause, all_params

    def parse_query(
        self,
        query_string: str,
        sort_by: str = "last_edited_at",
        sort_order: str = "desc",
    ) -> tuple[str, str, list[Any]]:
        if not self.schema_mapping:
            raise RuntimeError("QueryParser not set up.")

        if not query_string.strip():
            select_fields = self._build_dynamic_select_fields()
            select_query = f"""
                SELECT {select_fields}
                {self.from_and_joins}
                {self._build_order_by_clause(sort_by, sort_order)}
            """
            count_query = (
                f"SELECT COUNT(*) FROM {self.config['application']['main_table']}"
            )
            return count_query, select_query, []

        try:
            # Try to parse the query with the grammar
            ast = cast(
                AstNode, self.transformer.transform(self.parser.parse(query_string))
            )

            # Extract search terms from the AST for field optimization
            search_term = self._extract_search_term_from_ast(ast)

            # If parsing succeeds, use the normal translation
            global_search_fields = self._build_dynamic_global_search_fields(search_term)
            self.translator.reset(
                self.schema_mapping,
                global_search_fields,
                self.available_metadata_fields,
                self.string_fields,
                self.id_fields,
                self.entity_fields,
            )
            where_clause = self.translator.translate(ast)

        except exceptions.LarkError as e:
            # If parsing fails, try to parse valid parts and apply search to the rest
            logger.warning("Query parsing failed, using hybrid approach: %s", e)

            try:
                where_clause, params = self._build_hybrid_search_clause(query_string)
            except Exception as hybrid_error:
                logger.warning("Hybrid search failed: %s", hybrid_error)
                # Fallback to simple search only
                where_clause, params = self._build_fuzzy_search_clause(query_string)

            select_fields = self._build_dynamic_select_fields()
            select_query = f"""
                SELECT {select_fields}
                {self.from_and_joins}
                WHERE {where_clause}
                {self._build_order_by_clause(sort_by, sort_order)}
            """
            count_query = f"SELECT COUNT(*) {self.from_and_joins} WHERE {where_clause}"
            return count_query, select_query, params

        select_fields = self._build_dynamic_select_fields()
        select_query = f"""
            SELECT {select_fields}
            {self.from_and_joins}
            WHERE {where_clause}
            {self._build_order_by_clause(sort_by, sort_order)}
        """
        count_query = f"SELECT COUNT(*) {self.from_and_joins} WHERE {where_clause}"

        return count_query, select_query, self.translator.params

    def _build_order_by_clause(self, sort_by: str, sort_order: str) -> str:
        """
        Builds the ORDER BY clause for the query with proper field mapping.
        Supports sorting by entity fields, joined table fields, and metadata JSONB fields.
        """
        # Validate sort_order
        if sort_order.lower() not in ["asc", "desc"]:
            raise ValueError("sort_order must be 'asc' or 'desc'")

        # Handle metadata fields (e.g., "metadata.key" or "metadata.nested.key")
        if sort_by.startswith("metadata."):
            parts = sort_by.split(".", 1)  # Split into "metadata" and rest
            if len(parts) > 1:
                metadata_path = parts[1]
                # Split the metadata path by dots to handle nested keys
                path_parts = metadata_path.split(".")

                if len(path_parts) == 1:
                    # Simple metadata field: metadata.key
                    json_field = f"d.metadata->>{path_parts[0]!r}"
                else:
                    # Nested metadata field: metadata.nested.key
                    path_expression = "->".join(
                        [f"'{part}'" for part in path_parts[:-1]]
                    )
                    json_field = f"d.metadata->{path_expression}->>{path_parts[-1]!r}"

                # Add secondary sort by primary key for deterministic ordering
                # Get primary key from navigation analysis
                primary_key_field = (
                    f"d.{self.navigation_analysis['main_table_schema']['primary_key']}"
                )
                return f"ORDER BY {json_field} {sort_order.upper()}, {primary_key_field} {sort_order.upper()}"

        # Handle regular fields using the schema mapping
        field_obj = Field((sort_by,))
        try:
            sql_field = field_obj.to_sql(
                self.schema_mapping,
                available_metadata_fields=self.available_metadata_fields,
                string_fields=self.string_fields,
                id_fields=self.id_fields,
                entity_fields=self.entity_fields,
            )
            # Add secondary sort by primary key to ensure deterministic ordering
            # This prevents the same entity from appearing on multiple pages when there are ties
            primary_key_field = (
                f"d.{self.navigation_analysis['main_table_schema']['primary_key']}"
            )
            return f"ORDER BY {sql_field} {sort_order.upper()}, {primary_key_field} {sort_order.upper()}"
        except Exception as e:
            logger.error("Could not find the column to sort by: %s", e)
            raise e
