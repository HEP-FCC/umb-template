"""
Entity routes for the Universal Metadata Browser API.
Handles CRUD operations for entities and related data.
"""

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import BaseModel

from app.models.generic import GenericEntityUpdate
from app.storage.database import Database
from app.storage.schema_discovery import get_schema_discovery
from app.utils.auth_utils import AuthDependency, get_endpoint_required_role
from app.utils.config_utils import get_config
from app.utils.errors_utils import (
    SearchValidationError,
    field_error,
    not_found_error,
    operation_error,
    query_validation_error,
    validation_error,
)
from app.utils.gclql_query_parser_utils import QueryParser
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="", tags=["entities"])

# This will be injected from main.py
database: Database
query_parser: QueryParser

config = get_config()


def init_dependencies(db: Database, qp: QueryParser) -> None:
    """Initialize dependencies for this router."""
    global database, query_parser
    database = db
    query_parser = qp


class EntityRequest(BaseModel):
    """Request model for entity search"""

    filters: dict[str, str] = {}
    search: str = ""
    sort: str = "id"
    page: int = 1
    limit: int = 25


class EntityIdsRequest(BaseModel):
    """Request model for getting entities by IDs."""

    entity_ids: list[int]


class DeleteEntitiesRequest(BaseModel):
    """Request model for deleting entities by IDs."""

    entity_ids: list[int]


class SearchRequest(BaseModel):
    """Request model for generic search"""

    filters: dict[str, str] = {}
    search: str = ""
    page: int = 1
    limit: int = 25


@router.get("/query/", response_model=dict[str, Any])
async def execute_gclql_query(
    q: str,
    limit: int = Query(25, ge=20, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("last_edited_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
) -> Any:
    """
    Executes a GCLQL-style query against the database with infinite scroll support and sorting.
    Supports sorting by any entity field or metadata JSON field (e.g., 'metadata.key').
    """
    try:
        # Validate sort_order parameter
        if sort_order.lower() not in ["asc", "desc"]:
            raise validation_error(
                error_type="invalid_sort_order",
                message="sort_order must be 'asc' or 'desc'",
            )

        count_query, search_query, search_query_params = query_parser.parse_query(
            q, sort_by=sort_by, sort_order=sort_order.lower()
        )

        return await database.perform_search(
            count_query, search_query, search_query_params, limit, offset
        )

    except SearchValidationError as e:
        logger.warning(f"Query validation error: {e.message}")
        # Convert custom search validation error to standardized HTTP exception
        if e.error_type == "invalid_field":
            raise field_error(
                field_name=e.field_name or "unknown",
                message=e.message,
                user_message=e.user_message,
            )
        elif e.error_type == "invalid_operation":
            raise operation_error(
                operation=e.operation or "unknown",
                field_name=e.field_name,
                message=e.message,
                user_message=e.user_message,
            )
        else:
            raise query_validation_error(
                error_type=e.error_type,
                message=e.message,
                user_message=e.user_message
                or "Invalid search query. Please check your search syntax.",
            )
    except ValueError as e:
        logger.error("Invalid query", exc_info=True)
        raise validation_error(
            error_type="invalid_query", message=f"Invalid query: {e}"
        )


@router.post("/entities/", response_model=list[dict[str, Any]])
async def get_entities_by_ids(request: EntityIdsRequest) -> Any:
    """
    Get entities by their IDs with all details and metadata flattened to top-level keys.
    Takes a list of entity IDs and returns a list of entity information.
    """
    if not request.entity_ids:
        return []

    entities = await database.get_entities_by_ids(request.entity_ids)
    return entities


@router.get("/sorting-fields/", response_model=dict[str, Any])
async def get_sorting_fields() -> dict[str, Any]:
    """
    Get available fields for sorting in the query endpoint.
    Returns a flat list of all sortable fields for easy UI consumption.
    """
    result = await database.get_sorting_fields()
    return result


@router.get("/download-filtered/", response_model=list[dict[str, Any]])
async def download_filtered_entities(
    q: str,
    sort_by: str = Query("last_edited_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
) -> Any:
    """
    Download all entities matching the given query filter.
    This endpoint returns all results without pagination for download purposes.
    """
    logger.info(
        f"*** /download-filtered/ endpoint called with q={q}, sort_by={sort_by}, sort_order={sort_order}"
    )
    try:
        # Validate sort_order parameter
        if sort_order.lower() not in ["asc", "desc"]:
            raise validation_error(
                error_type="invalid_sort_order",
                message="sort_order must be 'asc' or 'desc'",
            )

        count_query, search_query, search_query_params = query_parser.parse_query(
            q, sort_by=sort_by, sort_order=sort_order.lower()
        )

        # Get all results by using a very large limit
        result = await database.perform_search(
            count_query, search_query, search_query_params, limit=999999, offset=0
        )

        # Return only the items array for download
        return result.get("items", [])

    except ValueError as e:
        logger.error("Invalid download query", exc_info=True)
        raise validation_error(
            error_type="invalid_query", message=f"Invalid query: {e}"
        )


@router.get("/entities/{entity_id}", response_model=dict[str, Any])
async def get_entity_by_id(entity_id: int) -> Any:
    """
    Get a single entity by its ID with all details and metadata flattened to top-level keys.
    """
    try:
        entity = await database.get_entity_by_id(entity_id)
        if not entity:
            raise not_found_error(
                error_type="entity_not_found",
                message=f"Entity with ID {entity_id} not found",
            )
        return entity
    except ValueError as e:
        raise validation_error(error_type="invalid_entity_id", message=str(e))


@router.put("/entities/{entity_id}", response_model=dict[str, Any])
async def update_entity(
    entity_id: int,
    update_data: GenericEntityUpdate,
    _request: Request,
    user: dict[str, Any] = Depends(
        AuthDependency(get_endpoint_required_role("update_entity"))
    ),
) -> Any:
    """
    Update an entity with the provided data.
    Requires authentication via session cookie.
    """
    try:
        logger.info(
            f"User {user.get('preferred_username', 'unknown')} updating entity {entity_id}."
        )

        update_dict = update_data.model_dump(exclude_none=True)

        if not update_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields provided for update",
            )

        updated_entity = await database.update_entity(
            entity_id, update_dict, user_info=user
        )
        return updated_entity
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class MetadataLockRequest(BaseModel):
    """Request model for locking/unlocking metadata fields."""

    field_name: str
    locked: bool


@router.put("/entities/{entity_id}/metadata/lock", response_model=dict[str, Any])
async def update_metadata_lock(
    entity_id: int,
    lock_request: MetadataLockRequest,
    _request: Request,
    user: dict[str, Any] = Depends(
        AuthDependency(get_endpoint_required_role("update_metadata_lock"))
    ),
) -> Any:
    """
    Update the lock state of a metadata field.
    Requires authentication via session cookie.
    """
    try:
        logger.info(
            f"User {user.get('preferred_username', 'unknown')} updating lock state for field '{lock_request.field_name}' "
            f"on entity {entity_id} to {'locked' if lock_request.locked else 'unlocked'}."
        )

        # Get current entity to check if it exists and get current metadata
        current_entity = await database.get_entity_by_id(entity_id)
        if not current_entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entity with ID {entity_id} not found",
            )

        # Get current metadata or initialize empty dict
        current_metadata = current_entity.get("metadata", {})
        if isinstance(current_metadata, str):
            import json

            current_metadata = json.loads(current_metadata)
        elif current_metadata is None:
            current_metadata = {}

        logger.info(f"Current metadata before lock update: {current_metadata}")
        logger.info(
            f"Current lock fields: {[k for k in current_metadata.keys() if '__lock__' in k]}"
        )

        # Create lock field name using the convention: __{key}__lock__
        lock_field_name = f"__{lock_request.field_name}__lock__"

        # Update lock state
        if lock_request.locked:
            # Set lock to True
            current_metadata[lock_field_name] = True
            logger.info(
                f"Locking field '{lock_request.field_name}' by setting {lock_field_name} = True"
            )
        else:
            # Remove lock field when unlocking
            if lock_field_name in current_metadata:
                current_metadata.pop(lock_field_name, None)
                logger.info(
                    f"Unlocking field '{lock_request.field_name}' by removing {lock_field_name}"
                )
            else:
                logger.info(f"Field '{lock_request.field_name}' was already unlocked")

        logger.info(f"Updated metadata keys: {list(current_metadata.keys())}")
        logger.info(
            f"Final lock fields: {[k for k in current_metadata.keys() if '__lock__' in k]}"
        )

        # Update the entity with only the lock field that changed
        lock_update: dict[str, bool | None]
        if lock_request.locked:
            # Only pass the new lock field
            lock_update = {lock_field_name: True}
        else:
            # For unlock, pass a special indicator to remove the field
            lock_update = {lock_field_name: None}  # None will indicate removal

        update_data = {"metadata": lock_update}
        logger.info(f"Sending update_data to database: {update_data}")

        await database.update_entity(entity_id, update_data, user_info=user)

        return {
            "success": True,
            "message": f"Field '{lock_request.field_name}' {'locked' if lock_request.locked else 'unlocked'} successfully",
            "field_name": lock_request.field_name,
            "locked": lock_request.locked,
            "entity_id": entity_id,
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating metadata lock: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.delete("/entities/", response_model=dict[str, Any])
async def delete_entities(
    request: DeleteEntitiesRequest,
    user: dict[str, Any] = Depends(
        AuthDependency(get_endpoint_required_role("delete_entities"))
    ),
) -> dict[str, Any]:
    """
    Delete entities by their IDs. Only users with 'authorized' role can perform this operation.

    This endpoint:
    - Validates user authentication and authorization (requires 'authorized' role)
    - Accepts a list of entity IDs for bulk deletion
    - Returns detailed results including success/failure counts
    - Handles foreign key constraints gracefully
    - Provides clear error messages for different failure scenarios
    """
    try:
        logger.info(
            f"User {user.get('preferred_username', 'unknown')} requesting deletion of entities: {request.entity_ids}"
        )

        if not request.entity_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No entity IDs provided for deletion",
            )

        # Validate entity IDs are positive integers
        invalid_ids = [entity_id for entity_id in request.entity_ids if entity_id <= 0]
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid entity IDs (must be positive integers): {invalid_ids}",
            )

        # Call the database delete method
        result = await database.delete_entities_by_ids(request.entity_ids)

        logger.info(
            # f"Delete operation completed for user {user.get('preferred_username', 'unknown')}: "
            f"{result['deleted_count']} deleted, {result['not_found_count']} not found"
        )

        return result

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        # Handle business logic errors (like foreign key constraints)
        logger.error(f"Business logic error during entity deletion: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during entity deletion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error occurred during deletion",
        )


class EntityOverrideResponse(BaseModel):
    """Response model for bulk entity override operations."""

    success: bool
    message: str
    updated_count: int = 0
    lock_conflicts: list[dict[str, Any]] = []
    updated_entities: list[dict[str, Any]] = []


@router.post("/override", response_model=EntityOverrideResponse)
async def override_entities(
    entities: list[dict[str, Any]],
    force_override: bool = Query(
        False, description="Force override even if metadata fields are locked"
    ),
    user: dict[str, Any] = Depends(
        AuthDependency(get_endpoint_required_role("override_entities"))
    ),
) -> EntityOverrideResponse:
    """
    Bulk entity metadata override endpoint with field locking and authentication.

    This endpoint performs METADATA-ONLY updates for security. It will reject attempts
    to update table columns such as foreign keys, UUIDs, names, or other database fields.
    Only metadata fields are processed and updated.

    REQUIRES: Each entity MUST include a valid 'uuid' field to identify the entity to update.
    No UUID computation is performed - entities without UUIDs will be rejected.

    When metadata is updated, fuzzy search capabilities are automatically maintained
    through PostgreSQL's expression indexes on the metadata column.

    Accepts a list of entity dictionaries to update. Each entity MUST:
    1. Include a 'uuid' field to match against existing entities

    All metadata updates are performed within a single transaction. If any entity
    cannot be found in the database or is missing a UUID, the entire operation fails
    and no changes are made. If any entity has locked metadata fields that conflict
    with the update, the entire operation is rolled back and detailed lock information
    is returned, unless force_override is set to True.

    Requires 'authorized' role for access.

    Args:
        entities: List of entity dictionaries with metadata fields to update
        force_override: If True, ignore metadata field locks and force the update
        user: Authenticated user data (injected by AuthDependency)

    Returns:
        EntityOverrideResponse with success status and either updated entities
        or detailed lock conflict information
    """

    try:
        logger.info(
            f"User {user.get('preferred_username', 'unknown')} attempting bulk override of {len(entities)} entities (force_override={force_override})."
        )

        # Validate that entities list is not empty
        if not entities:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No entities provided for override operation",
            )

        # Perform bulk override operation
        result = await database.bulk_override_entities(
            entities, user_info=user, force_override=force_override
        )

        return EntityOverrideResponse(
            success=result["success"],
            message=result["message"],
            updated_count=result.get("entities_processed", 0),
            lock_conflicts=result.get("lock_conflicts", []),
            updated_entities=result.get("updated_entities", []),
        )

    except ValueError as e:
        logger.error(f"Validation error in bulk override: {e}")
        raise validation_error(error_type="validation_error", message=str(e))
    except Exception as e:
        logger.error(f"Bulk override operation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during bulk override operation",
        )


@router.post("/search")
async def search_entities_generic(request: SearchRequest) -> Any:
    """
    Generic search endpoint that works with any database schema.
    Automatically handles joins based on schema discovery.
    """
    try:
        main_table = config["application"]["main_table"]

        async with database.session() as conn:
            schema_discovery = await get_schema_discovery(conn)
            navigation_analysis = await schema_discovery.analyze_navigation_structure(
                main_table
            )

            # Use the database method instead of direct SQL
            result = await database.search_entities(
                main_table,
                navigation_analysis,
                request.filters,
                request.search,
                request.page,
                request.limit,
            )
            return result

    except SearchValidationError as e:
        logger.warning(f"Search validation error: {e.message}")
        # Convert custom search validation error to standardized HTTP exception
        if e.error_type == "invalid_field":
            raise field_error(
                field_name=e.field_name or "unknown",
                message=e.message,
                user_message=e.user_message,
            )
        elif e.error_type == "invalid_operation":
            raise operation_error(
                operation=e.operation or "unknown",
                field_name=e.field_name,
                message=e.message,
                user_message=e.user_message,
            )
        else:
            raise query_validation_error(
                error_type=e.error_type,
                message=e.message,
                user_message=e.user_message
                or "Invalid search query. Please check your search syntax.",
            )
    except ValueError as e:
        logger.warning(f"Search value error: {e}")
        raise query_validation_error(
            message=str(e),
            user_message="Invalid search parameters. Please check your query and try again.",
        )
    except Exception as e:
        logger.error(f"Failed to perform generic search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Search failed"
        )
