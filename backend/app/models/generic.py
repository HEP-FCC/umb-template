"""
Generic models for schema-driven database entities.

These models work with any database schema by providing base classes and
standard patterns for entity creation and updates.
"""

import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DatabaseEntityBase(BaseModel):
    """Base model for any database entity with common fields."""

    # Every entity should have an ID and name
    id: int
    name: str

    # Optional common fields that many entities might have
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None
    last_edited_at: datetime.datetime | None = None
    edited_by_name: str | None = None

    # Metadata field for flexible additional data
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Allow any additional fields that might come from the database
    model_config = {"extra": "allow", "from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def parse_jsonb_as_dict(cls, data: Any) -> Any:
        """
        Ensures that if 'metadata' is returned as a JSON string from the DB,
        it's parsed into a dictionary.
        """
        if isinstance(data, dict) and isinstance(data.get("metadata"), str):
            import json

            try:
                data["metadata"] = json.loads(data["metadata"])
            except json.JSONDecodeError:
                # Let Pydantic handle the error if it's not valid JSON
                pass
        return data


class GenericEntityCreate(BaseModel):
    """Generic model for creating any entity."""

    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Allow any additional fields
    model_config = {"extra": "allow"}


class GenericEntityUpdate(BaseModel):
    """Generic model for updating any entity."""

    name: str | None = None
    metadata: dict[str, Any] | None = None

    # Allow any additional fields
    model_config = {"extra": "allow"}


# Export commonly used models
__all__ = [
    "DatabaseEntityBase",
    "GenericEntityCreate",
    "GenericEntityUpdate",
]
