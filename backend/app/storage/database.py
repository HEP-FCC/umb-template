"""
This file contains the Database class, which manages an asyncpg connection
pool and provides higher-level PostgreSQL database functions.
"""

from pathlib import Path
from typing import Any, TypeVar

import asyncpg
import inflect
from asyncpg.pool import Pool
from pydantic import BaseModel

# Import modularized database functions
from app.storage.database_modules.data_import_module import import_data
from app.storage.database_modules.entity_management_module import (
    bulk_override_entities,
    delete_entities_by_ids,
    update_entity,
)
from app.storage.database_modules.entity_retrieval_module import (
    get_entities_by_ids,
    get_entity_by_id,
)
from app.storage.database_modules.navigation_module import (
    get_dropdown_items,
    get_sorting_fields,
)
from app.storage.database_modules.schema_mapping_module import generate_schema_mapping
from app.storage.database_modules.search_module import (
    perform_search,
    search_entities,
)
from app.utils.config_utils import Config, get_config
from app.utils.logging_utils import get_logger

logger = get_logger()
T = TypeVar("T", bound=BaseModel)

# Load configuration once at module level
config = get_config()

# PostgreSQL advisory lock ID for schema migrations
# This lock ensures only one process applies schema changes at a time,
# preventing concurrent schema application from multiple workers.
SCHEMA_ADVISORY_LOCK_ID = int(
    config.get("database.schema_advisory_lock_id", 1234567890)
)


class AsyncSessionContextManager:
    """Async context manager for acquiring and releasing a connection from the pool."""

    def __init__(self, pool: Pool):
        self._pool = pool
        self._connection: asyncpg.Connection | None = None

    async def __aenter__(self) -> asyncpg.Connection:
        self._connection = await self._pool.acquire()
        return self._connection

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._connection is not None:
            await self._pool.release(self._connection)
            self._connection = None


class Database:
    def __init__(self) -> None:
        self._pool: Pool | None = None

    """
    Database interface for managing postgres connections using asyncpg, and providing
    higher-level PostgreSQL functions including schema setup, data management, and search.
    """

    async def setup(self, config: Config) -> None:
        """Creates the connection pool and initializes the database."""

        if self._pool:
            return

        self._inflect_engine = inflect.engine()
        self.config = config

        try:
            logger.info("Setting up the database...")
            await self._create_connection_pool()
            await self._apply_database_schema()
            logger.info("Database setup successfully.")
        except Exception as e:
            logger.error(f"Error setting up database: {e}")
            raise

    async def _create_connection_pool(self) -> None:
        """Creates the database connection pool."""
        connection_string = f"postgresql://{self.config['database.user']}:{self.config['database.password']}@{self.config['database.host']}:{self.config['database.port']}/{self.config['database.db']}"
        self._pool = await asyncpg.create_pool(
            dsn=connection_string, min_size=5, max_size=20
        )
        logger.info("Database connection pool created successfully.")

    async def _apply_database_schema(self) -> None:
        """Applies the database schema if not already applied."""
        schema_file = self.config.get(
            "database.schema_file", Path(__file__).parent / "database.sql"
        )

        with open(schema_file, encoding="utf-8") as f:
            schema_sql = f.read()

        async with self.session() as conn:
            await self._apply_schema_with_lock(conn, schema_sql)

    async def _apply_schema_with_lock(
        self, conn: asyncpg.Connection, schema_sql: str
    ) -> None:
        """Applies schema using advisory lock to prevent concurrent application."""
        # Use advisory lock to prevent concurrent schema application from multiple workers
        await conn.execute("SELECT pg_advisory_lock($1)", SCHEMA_ADVISORY_LOCK_ID)
        try:
            logger.info("Applying database schema...")
            async with conn.transaction():
                await conn.execute(schema_sql)
            logger.info("Database schema applied successfully")
        finally:
            # Release advisory lock
            await conn.execute("SELECT pg_advisory_unlock($1)", SCHEMA_ADVISORY_LOCK_ID)

    def _get_dynamic_primary_key(self, table_name: str) -> str:
        """
        Dynamically determine primary key column name from table name.

        Uses inflect library to convert plural table names to singular form
        and appends '_id' to create the primary key column name.

        Args:
            table_name: The name of the database table

        Returns:
            The primary key column name in format "{singular_table}_id"

        Examples:
            "authors" -> "author_id"
            "companies" -> "company_id"
            "categories" -> "category_id"
            "product" -> "product_id" (already singular)
        """
        if not self._inflect_engine:
            import inflect

            self._inflect_engine = inflect.engine()

        # Convert plural to singular if needed
        singular_name = self._inflect_engine.singular_noun(table_name)
        if singular_name:
            # Table name was plural, use singular form
            base_name = singular_name
        else:
            # Table name was already singular
            base_name = table_name

        return f"{base_name}_id"

    def session(self) -> AsyncSessionContextManager:
        """Create a new async context manager for database session."""
        if self._pool is None:
            raise RuntimeError(
                "Database connection pool not initialized. Call setup() first."
            )
        return AsyncSessionContextManager(self._pool)

    async def aclose(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # Delegated methods to modularized functions

    async def generate_schema_mapping(self) -> dict[str, str]:
        """Generate schema mapping for query parser."""
        return await generate_schema_mapping(self)

    async def get_entities_by_ids(self, entity_ids: list[int]) -> list[dict[str, Any]]:
        """Get entities by their IDs."""
        return await get_entities_by_ids(self, entity_ids)

    async def get_entity_by_id(self, entity_id: int) -> dict[str, Any] | None:
        """Get a single entity by ID."""
        return await get_entity_by_id(self, entity_id)

    async def update_entity(
        self,
        entity_id: int,
        update_data: dict[str, Any],
        user_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an entity."""
        return await update_entity(self, entity_id, update_data, user_info)

    async def delete_entities_by_ids(self, entity_ids: list[int]) -> dict[str, Any]:
        """Delete entities by IDs."""
        return await delete_entities_by_ids(self, entity_ids)

    async def bulk_override_entities(
        self,
        entities: list[dict[str, Any]],
        user_info: dict[str, Any] | None = None,
        force_override: bool = False,
    ) -> dict[str, Any]:
        """Bulk override entities."""
        return await bulk_override_entities(self, entities, user_info, force_override)

    async def perform_search(
        self,
        count_query: str,
        search_query: str,
        params: list[Any],
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """Perform search operation."""
        return await perform_search(
            self, count_query, search_query, params, limit, offset
        )

    async def search_entities(
        self,
        main_table: str,
        navigation_analysis: dict[str, Any],
        filters: dict[str, str] | None = None,
        search: str = "",
        page: int = 1,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search entities with fallback to metadata."""
        return await search_entities(
            self, main_table, navigation_analysis, filters, search, page, limit
        )

    async def get_sorting_fields(self) -> dict[str, Any]:
        """Get sorting fields for a table."""
        return await get_sorting_fields(self)

    async def get_dropdown_items(
        self,
        table_key: str,
        main_table: str,
        navigation_analysis: dict[str, Any],
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Get dropdown items for a field."""
        return await get_dropdown_items(
            self, table_key, main_table, navigation_analysis, filters
        )

    async def import_data(self, json_content: bytes) -> None:
        """Import data from JSON content."""
        return await import_data(self, json_content)
