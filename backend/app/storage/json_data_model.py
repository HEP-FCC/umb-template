"""
This file defines the Pydantic models used to parse and validate the
structure of the incoming JSON data dictionaries. It does not contain
any database logic.

USAGE FOR CUSTOM DATA FORMATS:
===============================

To add support for your custom data format:

1. Create your entity class by inheriting from BaseEntityData:
   ```python
   class MyCustomEntity(BaseEntityData):
       name: str
       type: str
       custom_field: str | None = None

       def get_all_metadata(self) -> dict[str, Any]:
           return {"type": self.type, "custom_field": self.custom_field}
   ```

2. Create your collection class by inheriting from BaseEntityCollection:
   ```python
   class MyCustomCollection(BaseEntityCollection):
       experiments: list[MyCustomEntity]

       def get_entities(self) -> list[BaseEntityData]:
           return self.experiments
   ```

3. Register your classes and detection rule:
   ```python
   def detect_my_format(raw_data: dict) -> bool:
       return "experiments" in raw_data and isinstance(raw_data["experiments"], list)

   EntityTypeRegistry.register_entity_class("MyCustomEntity", MyCustomEntity)
   EntityTypeRegistry.register_collection_class("MyCustomCollection", MyCustomCollection)
   EntityTypeRegistry.register_detection_rule(detect_my_format, MyCustomCollection)
   ```

The data import system will automatically detect and use your classes.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.logging_utils import get_logger

logger = get_logger()


class BaseEntityData(BaseModel, ABC):
    """
    Abstract base class for entity data that provides a common interface
    for all entity types that can be processed by the data import system.
    """

    @abstractmethod
    def get_all_metadata(self) -> dict[str, Any]:
        """
        Abstract method that must be implemented by all entity data classes.
        Should return all metadata for the entity as a dictionary.

        Returns:
            Dictionary containing all metadata fields for the entity
        """
        pass


# NOTE(required): Users must define their own data model class
# This is an example implementation - customize for your domain
class ExampleEntity(BaseEntityData):
    """
    Example Pydantic model for a single entity from the JSON dictionary.

    CUSTOMIZE THIS CLASS FOR YOUR DOMAIN:
    - Replace field names with your actual data fields
    - Update validation logic for your data types
    - Modify navigation entity fields to match your schema
    - Update get_all_metadata() to return your relevant metadata

    Core fields that are likely to be present are defined explicitly,
    while all other fields are stored in the raw_metadata for flexible handling.
    """

    # Example core fields - customize these for your domain
    name: str | None = Field(default=None, alias="title")
    description: str | None = Field(default=None)
    comment: str | None = Field(default=None)
    status: str | None = Field(default=None)
    size: int | None = Field(default=None)
    path: str | None = Field(default=None)

    # Example navigation entity fields - customize these to match your navigation tables
    category: str | None = Field(default=None)
    type: str | None = Field(
        default=None, alias="entity-type"
    )  # Example of alias usage
    source: str | None = Field(default=None)
    format: str | None = Field(default=None)

    # Store all other fields as metadata
    raw_metadata: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @field_validator(
        "title",
        "description",
        "comment",
        "status",
        "category",
        "type",
        "source",
        "format",
        mode="before",
    )
    @classmethod
    def handle_string_fields(cls, v: Any) -> str | None:
        """
        Handles string fields that might be missing, null, or need whitespace normalization.
        Returns None for null/empty values to avoid storing meaningless data.
        """
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        if isinstance(v, str):
            normalized = re.sub(r"\s+", " ", v.strip())
            return normalized if normalized else None
        return str(v) if v is not None else None

    @field_validator("size", mode="before")
    @classmethod
    def handle_int_fields(cls, v: Any) -> int | None:
        """
        Handles integer fields that might be missing or null.
        Returns None instead of raising an error for invalid values.
        """
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            logger.warning(f"Cannot parse integer value: {v}. Setting to None.")
            return None

    @field_validator("path", mode="before")
    @classmethod
    def handle_path_field(cls, v: Any) -> str | None:
        """
        Handles path field that might be missing or null.
        Returns None for empty/invalid paths.
        """
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        return str(v).strip() if v is not None else None

    @model_validator(mode="before")
    @classmethod
    def extract_metadata(cls, data: Any) -> Any:
        """
        Extract all fields not explicitly defined in the model into raw_metadata.
        This allows flexible handling of varying JSON structures.
        """
        if not isinstance(data, dict):
            return data

        # Fields that are explicitly handled by the model - UPDATE THESE FOR YOUR DOMAIN
        core_fields = {
            "title",
            "description",
            "comment",
            "status",
            "size",
            "path",
            "category",
            "type",
            "entity-type",  # alias for type
            "source",
            "format",
        }

        # Create a copy of the data for manipulation
        processed_data = data.copy()
        raw_metadata = {}

        # Extract all non-core fields into raw_metadata
        for key, value in data.items():
            if key not in core_fields:
                # Skip large/unwanted fields like 'files' if they exist
                if key != "files":
                    raw_metadata[key] = value

        # Add raw_metadata to the processed data
        processed_data["raw_metadata"] = raw_metadata

        return processed_data

    # NOTE(required): Users must define this function
    def get_all_metadata(self) -> dict[str, Any]:
        """
        Returns all metadata including both core fields and raw_metadata.
        Excludes None values and navigation entity fields (since they are stored in foreign key relationships).

        CUSTOMIZE THIS FOR YOUR DOMAIN:
        - Include/exclude fields based on what you want stored as metadata
        - Navigation fields (category, type, source, format) are typically excluded
          since they become foreign key relationships in the database
        """
        metadata: dict[str, Any] = {}

        # Add core fields that have values (excluding navigation fields)
        if self.name is not None:
            metadata["name"] = self.name
        if self.description is not None:
            metadata["description"] = self.description
        if self.comment is not None:
            metadata["comment"] = self.comment
        if self.status is not None:
            metadata["status"] = self.status
        if self.size is not None:
            metadata["size"] = self.size
        if self.path is not None:
            metadata["path"] = self.path

        # Add all raw metadata
        metadata.update(self.raw_metadata)

        return metadata


class BaseEntityCollection(BaseModel, ABC):
    """
    Abstract base class for entity collections that provides a common interface
    for all collection types that can be processed by the data import system.
    """

    @abstractmethod
    def get_entities(self) -> list[BaseEntityData]:
        """
        Abstract method that must be implemented by all entity collection classes.
        Should return a list of entities contained in the collection.

        Returns:
            List of BaseEntityData instances
        """
        pass


class ExampleEntityCollection(BaseEntityCollection):
    """
    Example Pydantic model for the root of the JSON dictionary.

    CUSTOMIZE THIS CLASS FOR YOUR DOMAIN:
    - Replace 'entities' field name with your actual collection field
    - Update the field type to match your entity class name
    - Update the get_entities() method to return your entities
    """

    entities: list[ExampleEntity]  # Customize the field name for your JSON structure

    def get_entities(self) -> list[BaseEntityData]:
        """
        Return the list of entities in this collection.

        Returns:
            List of BaseEntityData instances
        """
        return self.entities  # type: ignore[return-value]


class EntityTypeRegistry:
    """
    Registry for user-defined entity and collection classes.
    Users can register their custom classes here to make them discoverable
    by the data import system.
    """

    _entity_classes: dict[str, type[BaseEntityData]] = {}
    _collection_classes: dict[str, type[BaseEntityCollection]] = {}
    _detection_rules: list[
        tuple[Callable[[dict[str, Any]], bool], type[BaseEntityCollection]]
    ] = []

    @classmethod
    def register_entity_class(
        cls, name: str, entity_class: type[BaseEntityData]
    ) -> None:
        """Register a custom entity class."""
        cls._entity_classes[name] = entity_class

    @classmethod
    def register_collection_class(
        cls, name: str, collection_class: type[BaseEntityCollection]
    ) -> None:
        """Register a custom collection class."""
        cls._collection_classes[name] = collection_class

    @classmethod
    def register_detection_rule(
        cls,
        detection_func: Callable[[dict[str, Any]], bool],
        collection_class: type[BaseEntityCollection],
    ) -> None:
        """
        Register a detection rule that determines which collection class to use.

        Args:
            detection_func: Function that takes raw_data dict and returns True if this collection class should be used
            collection_class: The collection class to use if detection_func returns True
        """
        cls._detection_rules.append((detection_func, collection_class))

    @classmethod
    def detect_collection_class(
        cls, raw_data: dict[str, Any]
    ) -> type[BaseEntityCollection] | None:
        """
        Auto-detect the data format and return the appropriate collection class.

        Args:
            raw_data: Raw dictionary from JSON file

        Returns:
            Collection class or None if no suitable parser found
        """
        for detection_func, collection_class in cls._detection_rules:
            try:
                if detection_func(raw_data):
                    logger.debug(f"Detected format for {collection_class.__name__}")
                    return collection_class
            except Exception as e:
                logger.warning(f"Detection failed for {collection_class.__name__}: {e}")
                continue

        logger.warning("No suitable data format detected")
        return None

    @classmethod
    def get_entity_class(cls, name: str) -> type[BaseEntityData] | None:
        """Get a registered entity class by name."""
        return cls._entity_classes.get(name)

    @classmethod
    def get_collection_class(cls, name: str) -> type[BaseEntityCollection] | None:
        """Get a registered collection class by name."""
        return cls._collection_classes.get(name)

    @classmethod
    def get_default_collection_class(cls) -> type[BaseEntityCollection] | None:
        """Get the first registered collection class as default."""
        if cls._collection_classes:
            return next(iter(cls._collection_classes.values()))
        return None

    @classmethod
    def list_registered_classes(cls) -> dict[str, Any]:
        """List all registered classes for debugging."""
        return {
            "entities": cls._entity_classes.copy(),
            "collections": cls._collection_classes.copy(),
            "detection_rules": [
                (str(func), cls_type) for func, cls_type in cls._detection_rules
            ],
        }


# Example detection function - customize for your JSON format
def _detect_example_format(raw_data: dict[str, Any]) -> bool:
    """
    Detect if raw_data matches your entity format.

    CUSTOMIZE THIS FUNCTION FOR YOUR DOMAIN:
    - Update the field name from 'entities' to match your JSON structure
    - Add additional checks if needed to validate your format
    """
    return "entities" in raw_data and isinstance(raw_data["entities"], list)


# Auto-register the example classes - UPDATE THESE FOR YOUR DOMAIN
# Replace the class names and registry keys with your actual classes
EntityTypeRegistry.register_entity_class("ExampleEntity", ExampleEntity)
EntityTypeRegistry.register_collection_class(
    "ExampleEntityCollection", ExampleEntityCollection
)
EntityTypeRegistry.register_detection_rule(
    _detect_example_format, ExampleEntityCollection
)
