"""
Schema Discovery Module

This module provides functions to discover and analyze PostgreSQL database schema,
making it possible to automatically adapt the API to any database structure.
"""

from typing import Any

import asyncpg

from app.utils.logging_utils import get_logger

logger = get_logger()


class SchemaDiscovery:
    """Handles database schema discovery and analysis."""

    def __init__(self, connection: asyncpg.Connection):
        self.connection = connection

    async def get_complete_schema(self) -> dict[str, Any]:
        """
        Get complete database schema information including tables, columns, and relationships.

        Returns:
            Dictionary containing complete schema information
        """
        try:
            tables = await self._get_all_tables()
            foreign_keys = await self._get_all_foreign_keys()

            # Enhance table info with foreign key relationships
            for table_name, table_info in tables.items():
                for column in table_info["columns"]:
                    # Find foreign key relationships for this column
                    fk_info = next(
                        (
                            fk
                            for fk in foreign_keys
                            if fk["table_name"] == table_name
                            and fk["column_name"] == column["column_name"]
                        ),
                        None,
                    )

                    if fk_info:
                        column["is_foreign_key"] = True
                        column["referenced_table"] = fk_info["referenced_table"]
                        column["referenced_column"] = fk_info["referenced_column"]
                    else:
                        column["is_foreign_key"] = False

            return {"tables": tables, "foreign_keys": foreign_keys}

        except Exception as e:
            logger.error(f"Failed to discover database schema: {e}")
            raise

    async def _get_all_tables(self) -> dict[str, dict[str, Any]]:
        """Get all tables with their column information."""
        query = """
            SELECT
                t.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                CASE
                    WHEN pk.column_name IS NOT NULL THEN true
                    ELSE false
                END as is_primary_key,
                c.column_default,
                c.ordinal_position
            FROM information_schema.tables t
            JOIN information_schema.columns c ON t.table_name = c.table_name
            LEFT JOIN (
                SELECT
                    tc.table_name,
                    kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
            ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
            WHERE
                t.table_schema = 'public'
                AND t.table_type = 'BASE TABLE'
                AND t.table_name NOT LIKE 'pg_%'
                AND t.table_name NOT LIKE 'sql_%'
            ORDER BY t.table_name, c.ordinal_position;
        """

        rows = await self.connection.fetch(query)
        tables = {}

        for row in rows:
            table_name = row["table_name"]
            if table_name not in tables:
                tables[table_name] = {
                    "table_name": table_name,
                    "columns": [],
                    "primary_key": None,
                }

            column_info = {
                "column_name": row["column_name"],
                "data_type": row["data_type"],
                "is_nullable": row["is_nullable"] == "YES",
                "is_primary_key": row["is_primary_key"],
                "column_default": row["column_default"],
                "ordinal_position": row["ordinal_position"],
            }

            tables[table_name]["columns"].append(column_info)

            if row["is_primary_key"]:
                tables[table_name]["primary_key"] = row["column_name"]

        return tables

    async def _get_all_foreign_keys(self) -> list[dict[str, str]]:
        """Get all foreign key relationships."""
        query = """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS referenced_table,
                ccu.column_name AS referenced_column,
                tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = 'public'
            ORDER BY tc.table_name, kcu.column_name;
        """

        rows = await self.connection.fetch(query)
        return [dict(row) for row in rows]

    async def get_table_metadata(self, table_name: str) -> dict[str, Any] | None:
        """Get metadata for a specific table."""
        schema = await self.get_complete_schema()
        result = schema["tables"].get(table_name)
        if result is None:
            return None
        # Ensure the result is properly typed as dict[str, Any]
        return dict(result) if isinstance(result, dict) else None

    async def get_foreign_key_dependencies(
        self, table_name: str
    ) -> list[dict[str, str]]:
        """Get all foreign key dependencies for a specific table."""
        foreign_keys = await self._get_all_foreign_keys()
        return [fk for fk in foreign_keys if fk["table_name"] == table_name]

    async def analyze_navigation_structure(self, main_table: str) -> dict[str, Any]:
        """
        Analyze the navigation structure based on a main table's foreign keys.

        Args:
            main_table: The name of the main table (e.g., 'entities')

        Returns:
            Dictionary containing navigation analysis
        """
        try:
            schema = await self.get_complete_schema()

            if main_table not in schema["tables"]:
                raise ValueError(f"Main table '{main_table}' not found in schema")

            main_table_info = schema["tables"][main_table]

            # Find all foreign key columns in the main table
            navigation_entities = []
            for column in main_table_info["columns"]:
                if column["is_foreign_key"]:
                    entity_key = column["column_name"].replace("_id", "")
                    navigation_entities.append(
                        {
                            "key": entity_key,
                            "table_name": column["referenced_table"],
                            "column_name": column["column_name"],
                            "referenced_table": column["referenced_table"],
                            "referenced_column": column["referenced_column"],
                            "is_required": not column["is_nullable"],
                            "order": column["ordinal_position"],
                        }
                    )

            # Sort by order for consistent navigation hierarchy
            navigation_entities.sort(key=lambda x: x["order"])

            # Get metadata for each navigation table
            navigation_tables = {}
            for entity in navigation_entities:
                table_info = schema["tables"].get(entity["referenced_table"])
                if table_info:
                    # Find the name column (prefer 'name', fallback to first text column)
                    name_column = "name"
                    text_columns = [
                        col
                        for col in table_info["columns"]
                        if "text" in col["data_type"].lower()
                        or "varchar" in col["data_type"].lower()
                    ]

                    if (
                        not any(
                            col["column_name"] == "name"
                            for col in table_info["columns"]
                        )
                        and text_columns
                    ):
                        name_column = text_columns[0]["column_name"]

                    navigation_tables[entity["key"]] = {
                        "table_name": entity["referenced_table"],
                        "primary_key": table_info["primary_key"],
                        "name_column": name_column,
                        "columns": [
                            col["column_name"] for col in table_info["columns"]
                        ],
                    }

            return {
                "main_table": main_table,
                "main_table_schema": main_table_info,
                "navigation_entities": navigation_entities,
                "navigation_tables": navigation_tables,
                "navigation_order": [entity["key"] for entity in navigation_entities],
            }

        except Exception as e:
            logger.error(
                f"Failed to analyze navigation structure for {main_table}: {e}"
            )
            raise


async def get_schema_discovery(connection: asyncpg.Connection) -> SchemaDiscovery:
    """Factory function to create a SchemaDiscovery instance."""
    return SchemaDiscovery(connection)
