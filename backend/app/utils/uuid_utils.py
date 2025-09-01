"""
UUID generation utilities for the Universal Metadata Browser Template.

This module provides utilities for generating deterministic UUIDs for entities
and other entities in the metadata database.
"""

import uuid

from app.utils.config_utils import get_config

# Load configuration once at module level
config = get_config()

# UUID namespace for entity identification
# This namespace creates deterministic UUIDs for entities based on your project
# identifier and version. For versioning: YourProjectv01 -> this namespace, YourProjectv02 -> different namespace.
ENTITY_UUID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_DNS,
    config.get("database.entity_uuid_namespace", "entity_uuid_namespace.v01"),
)


def generate_entity_uuid(
    entity_name: str,
    **foreign_key_ids: int | None,
) -> str:
    """
    Generate deterministic UUID for an entity based on key identifying fields.

    Uses UUID5 (SHA-1 based) to ensure the same input always generates the same UUID.
    The namespace is derived from your project domain and version (v01).

    Args:
        entity_name: The entity name
        **foreign_key_ids: Variable foreign key IDs (e.g., category_id=1, type_id=2)

    Returns:
        String representation of the generated UUID

    Example:
        >>> generate_entity_uuid("my_entity", category_id=1, type_id=2)
        'a1b2c3d4-e5f6-5789-abcd-ef1234567890'
    """
    # Sort the foreign key IDs by key name for consistent ordering
    sorted_keys = sorted(foreign_key_ids.keys())

    # Convert None values to string "0" and IDs to strings, in sorted order
    foreign_key_parts = []
    for key in sorted_keys:
        value = foreign_key_ids[key]
        value_str = str(value) if value is not None else "0"
        foreign_key_parts.append(value_str)

    foreign_keys_str = ",".join(foreign_key_parts)

    # Create the deterministic name for UUID5 generation
    uuid_name = f"{entity_name},{foreign_keys_str}"

    # Generate deterministic UUID5 using your project namespace
    entity_uuid = uuid.uuid5(ENTITY_UUID_NAMESPACE, uuid_name)

    return str(entity_uuid)
