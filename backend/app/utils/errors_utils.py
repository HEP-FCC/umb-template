"""
Standardized Error Handling for Universal Metadata Browser Backend
Provides consistent error response formats matching frontend expectations
"""

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel


class SearchValidationError(Exception):
    """Custom exception for search validation errors."""

    def __init__(
        self,
        message: str,
        error_type: str = "invalid_query",
        field_name: str | None = None,
        operation: str | None = None,
        user_message: str | None = None,
    ):
        self.message = message
        self.error_type = error_type
        self.field_name = field_name
        self.operation = operation
        self.user_message = user_message
        super().__init__(message)


# Error type constants that match frontend global-error-handler.client.ts
class ErrorTypes:
    """Error type constants for consistent error responses."""

    # Authentication errors (401)
    AUTHENTICATION_FAILED = "authentication_failed"
    SESSION_ERROR = "session_error"
    NO_REFRESH_TOKEN = "no_refresh_token"
    REFRESH_FAILED = "refresh_failed"

    # Validation errors (400)
    INVALID_INPUT = "invalid_input"
    INVALID_QUERY = "invalid_query"
    INVALID_FIELD = "invalid_field"
    INVALID_OPERATION = "invalid_operation"
    INVALID_SYNTAX = "invalid_syntax"

    # Client errors (4xx)
    NOT_FOUND = "not_found"

    # Server errors (5xx)
    INTERNAL_ERROR = "internal_error"


class ErrorDetail(BaseModel):
    """Error detail structure for standardized error responses."""

    error: str  # Error type identifier (required)
    message: str  # Detailed technical message (required)
    code: str | None = None  # Specific error code
    required_role: str | None = None  # For 403 authorization
    validation_errors: dict[str, list[str]] | None = None  # For 400 validation


class StandardErrorResponse(BaseModel):
    """Standard error response format that matches frontend expectations."""

    message: str  # User-friendly message
    status: int  # HTTP status code
    details: ErrorDetail


def create_standard_http_exception(
    status_code: int,
    error_type: str,
    user_message: str,
    technical_message: str,
    code: str | None = None,
    required_role: str | None = None,
    validation_errors: dict[str, list[str]] | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    """
    Create a standardized HTTPException with consistent error format.

    Args:
        status_code: HTTP status code
        error_type: Error type from ErrorTypes constants
        user_message: User-friendly message for frontend display
        technical_message: Detailed technical message for debugging
        code: Optional specific error code
        required_role: Optional required role (for 403 errors)
        validation_errors: Optional validation error details (for 400 errors)
        headers: Optional HTTP headers

    Returns:
        HTTPException with standardized error format
    """
    detail: dict[str, Any] = {
        "message": user_message,
        "status": status_code,
        "details": {
            "error": error_type,
            "message": technical_message,
        },
    }

    # Add optional fields if provided
    details: dict[str, Any] = detail["details"]
    if code:
        details["code"] = code
    if required_role:
        details["required_role"] = required_role
    if validation_errors:
        details["validation_errors"] = validation_errors

    return HTTPException(status_code=status_code, detail=detail, headers=headers)


# Convenience functions for common error types


def unauthenticated_error(
    error_type: str = ErrorTypes.AUTHENTICATION_FAILED,
    message: str = "Authentication failed",
    user_message: str = "Your session has expired. Please log in again.",
    headers: dict[str, str] | None = None,
) -> HTTPException:
    """
    Create a standardized 401 Unauthenticated error.
    Used when we cannot verify the user's identity:
    - Invalid/missing credentials
    - Expired tokens
    - Malformed authentication data
    """
    error_headers = headers or {"WWW-Authenticate": "Bearer"}
    return create_standard_http_exception(
        status_code=status.HTTP_401_UNAUTHORIZED,
        error_type=error_type,
        user_message=user_message,
        technical_message=message,
        headers=error_headers,
    )


def validation_error(
    error_type: str = ErrorTypes.INVALID_INPUT,
    message: str = "Request validation failed",
    user_message: str = "Invalid request data. Please check your input.",
    validation_errors: dict[str, list[str]] | None = None,
) -> HTTPException:
    """Create a standardized 400 validation error."""
    return create_standard_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_type=error_type,
        user_message=user_message,
        technical_message=message,
        validation_errors=validation_errors,
    )


def not_found_error(
    error_type: str = ErrorTypes.NOT_FOUND,
    message: str = "Resource not found in database",
    user_message: str = "The requested resource was not found",
) -> HTTPException:
    """Create a standardized 404 not found error."""
    return create_standard_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        error_type=error_type,
        user_message=user_message,
        technical_message=message,
    )


def server_error(
    error_type: str = ErrorTypes.INTERNAL_ERROR,
    message: str = "Internal server error",
    user_message: str = "An internal server error occurred. Please try again later.",
) -> HTTPException:
    """Create a standardized 500 server error."""
    return create_standard_http_exception(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_type=error_type,
        user_message=user_message,
        technical_message=message,
    )


def query_validation_error(
    error_type: str = ErrorTypes.INVALID_QUERY,
    message: str = "Query validation failed",
    user_message: str = "Invalid search query. Please check your search syntax.",
    validation_errors: dict[str, list[str]] | None = None,
) -> HTTPException:
    """Create a standardized 400 query validation error."""
    return create_standard_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_type=error_type,
        user_message=user_message,
        technical_message=message,
        validation_errors=validation_errors,
    )


def field_error(
    field_name: str,
    error_type: str = ErrorTypes.INVALID_FIELD,
    message: str | None = None,
    user_message: str | None = None,
) -> HTTPException:
    """Create a standardized 400 field validation error."""
    if not message:
        message = f"Field '{field_name}' is not valid"
    if not user_message:
        user_message = f"The field '{field_name}' is not available for searching. Please check the field name and try again."

    return create_standard_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_type=error_type,
        user_message=user_message,
        technical_message=message,
        validation_errors={"field": [f"'{field_name}' is not a valid field"]},
    )


def operation_error(
    operation: str,
    field_name: str | None = None,
    error_type: str = ErrorTypes.INVALID_OPERATION,
    message: str | None = None,
    user_message: str | None = None,
) -> HTTPException:
    """Create a standardized 400 operation validation error."""
    if not message:
        if field_name:
            message = (
                f"Operation '{operation}' is not supported for field '{field_name}'"
            )
        else:
            message = f"Operation '{operation}' is not supported"

    if not user_message:
        if field_name:
            user_message = f"The operation '{operation}' cannot be used with the field '{field_name}'. Please use a different operator."
        else:
            user_message = f"The operation '{operation}' is not supported. Please use a different operator."

    return create_standard_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_type=error_type,
        user_message=user_message,
        technical_message=message,
        validation_errors={
            "operation": [f"'{operation}' is not valid for this context"]
        },
    )
