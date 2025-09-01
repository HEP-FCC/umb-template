"""
Navigation and schema discovery routes for the Universal Metadata Browser API.
Handles dynamic schema discovery and dropdown data for navigation.
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.storage.database import Database
from app.storage.schema_discovery import get_schema_discovery
from app.utils.config_utils import get_config
from app.utils.errors_utils import server_error
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="", tags=["navigation"])

# This will be injected from main.py
database: Database

config = get_config()


def init_dependencies(db: Database) -> None:
    """Initialize dependencies for this router."""
    global database
    database = db


def _get_navigation_config_from_config(
    config: Any, navigation_analysis: dict[str, Any]
) -> dict[str, Any]:
    """
    Extract navigation configuration from the config file.
    This function is used by the schema endpoint to build navigation menus.
    """
    navigation_config = config.get("navigation", {})
    navigation_tables = navigation_analysis["navigation_tables"]

    # Get navigation order from config, fallback to alphabetical
    config_order = navigation_config.get("order", [])
    if config_order:
        # Validate that config order keys exist in navigation_tables
        valid_keys = [key for key in config_order if key in navigation_tables]
        # Add any missing keys at the end
        remaining_keys = [
            key for key in navigation_tables.keys() if key not in valid_keys
        ]
        ordered_keys = valid_keys + remaining_keys
    else:
        # Fallback to alphabetical order
        ordered_keys = sorted(navigation_tables.keys())

    # Build minimal navigation config - frontend will derive colors, icons, labels
    navigation_configs = {}
    for i, key in enumerate(ordered_keys):
        if key in navigation_tables:
            entity_info = next(
                e for e in navigation_analysis["navigation_entities"] if e["key"] == key
            )
            navigation_configs[key] = {
                "columnName": entity_info["column_name"],
                "orderIndex": i,  # Frontend will use this to derive color from app config
            }

    return {"order": ordered_keys, "config": navigation_configs}


@router.get("/schema")
async def get_database_schema() -> Any:
    """
    Get the complete database schema configuration for frontend.
    This endpoint analyzes the database structure and returns configuration
    that allows the frontend to work with any database schema.
    """
    try:
        main_table = config["application"]["main_table"]

        async with database.session() as conn:
            schema_discovery = await get_schema_discovery(conn)

            # Analyze the navigation structure based on the main table
            navigation_analysis = await schema_discovery.analyze_navigation_structure(
                main_table
            )

            # Fetch navigation configuration from config file
            navigation_config = _get_navigation_config_from_config(
                config, navigation_analysis
            )

            # Build the response
            schema_config = {
                "tables": [navigation_analysis["main_table"]]
                + list(navigation_analysis["navigation_tables"].keys()),
                "main_table": navigation_analysis["main_table"],
                "foreign_keys": [
                    f"{key}_id"
                    for key in navigation_analysis["navigation_tables"].keys()
                ],
                "navigation_config": {
                    "order": navigation_config["order"],
                    "menu": navigation_config[
                        "config"
                    ],  # Only return what exists in DB
                },
                "mainTableSchema": {
                    "tableName": navigation_analysis["main_table"],
                    "primaryKey": navigation_analysis["main_table_schema"][
                        "primary_key"
                    ],
                    "nameColumn": "name",  # Entities typically use 'name'
                    "columns": [
                        col["column_name"]
                        for col in navigation_analysis["main_table_schema"]["columns"]
                    ],
                },
                "navigationTables": navigation_analysis["navigation_tables"],
                "navigationOrder": navigation_config["order"],
                "navigation": navigation_config["config"],
                "appTitle": config.get("application", {}).get(
                    "title", "Metadata Browser"
                ),
                "searchPlaceholder": config.get("application", {}).get(
                    "search_placeholder", f"Search {main_table}..."
                ),
            }

            return schema_config

    except Exception as e:
        logger.error(f"Failed to get database schema: {e}")
        raise server_error(
            error_type="schema_error", message="Failed to retrieve database schema"
        )


@router.get("/dropdown/{table_key}")
async def get_dropdown_items(
    table_key: str,
    filters: str = Query("", description="JSON string of filters to apply"),
) -> Any:
    """
    Get dropdown options for navigation filters.
    Supports filtered results based on other selected navigation options.
    """
    try:
        config = get_config()
        main_table = config["application"]["main_table"]

        # Parse filters from query parameter
        filter_dict = {}
        if filters:
            try:
                filter_dict = json.loads(filters)
            except json.JSONDecodeError:
                logger.warning(f"Invalid filters JSON: {filters}")

        async with database.session() as conn:
            schema_discovery = await get_schema_discovery(conn)

            if table_key == "main":
                # Handle main table dropdown (unlikely but possible)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Main table dropdown not supported",
                )
            else:
                # Handle navigation table dropdown
                navigation_analysis = (
                    await schema_discovery.analyze_navigation_structure(main_table)
                )

                if table_key not in navigation_analysis["navigation_tables"]:
                    raise ValueError(f"Table '{table_key}' not found in navigation")

                # Get dropdown data using the database method
                dropdown_data = await database.get_dropdown_items(
                    table_key, main_table, navigation_analysis, filter_dict
                )

                return dropdown_data

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get dropdown items for {table_key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load {table_key} options",
        )
