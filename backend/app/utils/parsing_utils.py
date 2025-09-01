"""
Generic parsing utilities for handling different data types automatically.

This module provides utilities to automatically parse and convert data types
without hardcoding field-specific logic, including date/timestamp parsing,
numeric parsing, and array/list parsing.
"""

import json
import re
from datetime import date, datetime
from typing import Any

from app.utils.logging_utils import get_logger

logger = get_logger()


def try_parse_date_value(value: Any) -> date | datetime | Any:
    """
    Try to parse a value as a date/timestamp. If successful, return the parsed
    date/datetime object. If parsing fails, return the original value unchanged.

    This function is designed to be safe and non-destructive - it only converts
    values that are clearly dates/timestamps, leaving all other values untouched.

    Args:
        value: Any value that might be a date/timestamp string

    Returns:
        date/datetime object if parsing succeeds, original value otherwise
    """
    # Only process string values
    if not isinstance(value, str):
        return value

    # Skip empty or very short strings
    cleaned_value = value.strip()
    if len(cleaned_value) < 8:  # Minimum for "YYYY-MM-DD"
        return value

    # Quick pre-filter: Check if string looks like a date/timestamp
    if not _looks_like_date_string(cleaned_value):
        return value

    # Try to parse the date string
    try:
        parsed_date = _parse_date_string(cleaned_value)

        # Validate the parsed date is reasonable (not too far in past/future)
        # Return date object for date-only values, datetime for time values
        if isinstance(parsed_date, datetime) and _is_date_only(cleaned_value):
            return parsed_date.date()
        return parsed_date

    except (ValueError, TypeError) as e:
        logger.debug(f"Could not parse '{value}' as date: {e}")
        return value


def _looks_like_date_string(value: str) -> bool:
    """
    Quick check if a string looks like it could be a date/timestamp.
    Uses regex patterns to avoid expensive parsing attempts on non-date strings.
    """
    # Common date/timestamp patterns
    date_patterns = [
        r"^\d{4}-\d{1,2}-\d{1,2}$",  # YYYY-MM-DD
        r"^\d{4}-\d{1,2}-\d{1,2}[T ]\d{1,2}:\d{1,2}",  # YYYY-MM-DD HH:MM or YYYY-MM-DDTHH:MM
        r"^\d{1,2}/\d{1,2}/\d{4}$",  # MM/DD/YYYY or DD/MM/YYYY
        r"^\d{1,2}-\d{1,2}-\d{4}$",  # MM-DD-YYYY or DD-MM-YYYY
        r"^\d{4}/\d{1,2}/\d{1,2}$",  # YYYY/MM/DD
        r"^\d{10}$",  # Unix timestamp (10 digits)
        r"^\d{13}$",  # Unix timestamp in milliseconds (13 digits)
    ]

    return any(re.match(pattern, value) for pattern in date_patterns)


def _is_date_only(date_string: str) -> bool:
    """Check if the date string contains only date (no time) information."""
    return "T" not in date_string and ":" not in date_string


def _parse_date_string(date_str: str) -> datetime:
    """
    Parse a date string in various formats to a datetime object.

    This is an enhanced version of the existing parse_date_string function
    with additional format support and better error handling.
    """
    # Remove quotes if present
    date_str = date_str.strip("\"'")

    # Handle Unix timestamps
    if date_str.isdigit():
        timestamp = float(date_str)
        # If it's a 13-digit number, it's likely milliseconds
        if len(date_str) == 13:
            timestamp = timestamp / 1000
        # If it's a 10-digit number, it's likely seconds
        elif len(date_str) == 10:
            timestamp = timestamp
        else:
            raise ValueError(f"Unrecognized timestamp format: {date_str}")

        return datetime.fromtimestamp(timestamp)

    # List of supported formats (ordered from most specific to least specific)
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",  # "2025-07-20T15:30:00.123Z" (ISO with microseconds and Z)
        "%Y-%m-%dT%H:%M:%S.%f",  # "2025-07-20T15:30:00.123" (ISO with microseconds)
        "%Y-%m-%dT%H:%M:%SZ",  # "2025-07-20T15:30:00Z" (ISO with Z)
        "%Y-%m-%dT%H:%M:%S",  # "2025-07-20T15:30:00" (ISO format)
        "%Y-%m-%d %H:%M:%S.%f",  # "2025-07-20 15:30:00.123" (with microseconds)
        "%Y-%m-%d %H:%M:%S",  # "2025-07-20 15:30:00" (date and time)
        "%Y-%m-%dT%H:%M",  # "2025-07-20T15:30" (ISO without seconds)
        "%Y-%m-%d %H:%M",  # "2025-07-20 15:30" (without seconds)
        "%Y-%m-%d",  # "2025-07-20" (date only)
        "%m/%d/%Y",  # "07/20/2025" (US format)
        "%d/%m/%Y",  # "20/07/2025" (EU format)
        "%m-%d-%Y",  # "07-20-2025" (US format with dashes)
        "%d-%m-%Y",  # "20-07-2025" (EU format with dashes)
        "%Y/%m/%d",  # "2025/07/20" (ISO-ish with slashes)
        "%B %d, %Y",  # "July 20, 2025" (full month name)
        "%b %d, %Y",  # "Jul 20, 2025" (abbreviated month)
        "%d %B %Y",  # "20 July 2025" (EU style with full month)
        "%d %b %Y",  # "20 Jul 2025" (EU style with abbreviated month)
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # If none of the formats work, raise an error
    raise ValueError(f"Unable to parse date string: {date_str}")


def process_entity_data_for_dates(data: Any) -> Any:
    """
    Process entity data dictionary and convert any string date/timestamp values
    to proper Python date/datetime objects.

    This function recursively processes the data structure and converts
    date strings while leaving all other data unchanged.

    Args:
        data: Dictionary or other data structure containing entity data

    Returns:
        Data structure with date strings converted to date/datetime objects
    """
    if isinstance(data, dict):
        processed_data = {}

        for key, value in data.items():
            if isinstance(value, dict):
                # Recursively process nested dictionaries
                processed_data[key] = process_entity_data_for_dates(value)
            elif isinstance(value, list):
                # Process lists (but don't try to parse list elements as dates unless they're strings)
                processed_data[key] = [
                    try_parse_date_value(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                # Try to parse the value as a date
                processed_data[key] = try_parse_date_value(value)

        return processed_data
    else:
        # For non-dict data, just try to parse it directly
        return try_parse_date_value(data)


def try_parse_numeric_value(value: Any) -> int | float | Any:
    """
    Try to parse a value as a numeric type (int or float).

    Returns the parsed numeric value if successful, otherwise returns the original value.
    """
    if value is None or value == "":
        return None

    # If already a number, return as-is
    if isinstance(value, int | float):
        return value

    # Convert to string for parsing
    str_value = str(value).strip()
    if not str_value:
        return None

    try:
        # Try integer first
        if "." not in str_value and "e" not in str_value.lower():
            return int(str_value)
        else:
            return float(str_value)
    except (ValueError, TypeError):
        # If parsing fails, return original value
        return value


def try_parse_array_value(value: Any) -> list[str] | Any:
    """
    Try to parse a value as an array/list.

    Handles various input formats:
    - Already a list: return as-is (if non-empty)
    - String that looks like JSON array: parse it
    - Non-empty string: convert to single-item list
    - Empty/null values: return None

    Returns the parsed list if successful, otherwise returns the original value.
    """
    if value is None or value == "":
        return None

    # If already a list, validate it's not empty
    if isinstance(value, list):
        if len(value) > 0:
            # Convert all items to strings and filter out empty ones
            filtered_items = [str(item).strip() for item in value if str(item).strip()]
            return filtered_items if filtered_items else None
        else:
            return None

    # Convert to string for parsing
    str_value = str(value).strip()
    if not str_value:
        return None

    # Try to parse as JSON array
    if str_value.startswith("[") and str_value.endswith("]"):
        try:
            parsed = json.loads(str_value)
            if isinstance(parsed, list) and len(parsed) > 0:
                # Convert all items to strings and filter out empty ones
                filtered_items = [
                    str(item).strip() for item in parsed if str(item).strip()
                ]
                return filtered_items if filtered_items else None
        except (json.JSONDecodeError, TypeError):
            pass

    # Try comma-separated values
    if "," in str_value:
        items = [item.strip() for item in str_value.split(",")]
        filtered_items = [item for item in items if item]
        if filtered_items:
            return filtered_items

    # Single non-empty string - convert to single-item list
    return [str_value]


def try_parse_value_auto(value: Any) -> Any:
    """
    Automatically try to parse a value using different parsing strategies.

    Order of parsing attempts:
    1. Date/timestamp parsing
    2. Numeric parsing (for fields that look numeric)
    3. Array parsing (for fields that might be arrays)
    4. Return original value

    Args:
        value: The value to parse

    Returns:
        The best-parsed version of the value
    """
    if value is None or value == "":
        return None

    # First try date parsing
    date_result = try_parse_date_value(value)
    if isinstance(date_result, date | datetime):
        return date_result

    # If it's a string, try other parsing methods
    if isinstance(value, str):
        str_value = value.strip()

        # Try numeric parsing for strings that look like numbers
        if _looks_like_number(str_value):
            numeric_result = try_parse_numeric_value(value)
            if isinstance(numeric_result, int | float):
                return numeric_result

        # Try array parsing for strings that might be arrays
        if _looks_like_array(str_value):
            array_result = try_parse_array_value(value)
            if isinstance(array_result, list):
                return array_result

    # If it's already a list, try array parsing
    elif isinstance(value, list):
        array_result = try_parse_array_value(value)
        if array_result is not None:
            return array_result

    # For numeric types, try numeric parsing
    elif isinstance(value, int | float):
        return try_parse_numeric_value(value)

    # Return original value if no parsing worked
    return value


def _looks_like_number(value: str) -> bool:
    """Check if a string looks like it could be a number."""
    if not value.strip():
        return False

    # Remove common numeric characters
    test_value = value.strip().replace(",", "").replace(" ", "")

    # Check for basic numeric patterns
    try:
        float(test_value)
        return True
    except ValueError:
        return False


def _looks_like_array(value: str) -> bool:
    """Check if a string looks like it could be an array."""
    if not value.strip():
        return False

    value = value.strip()

    # JSON array format
    if value.startswith("[") and value.endswith("]"):
        return True

    # Comma-separated values (but not if it looks like a sentence)
    if "," in value:
        # Simple heuristic: if it has commas but no common sentence words
        sentence_indicators = [
            " and ",
            " or ",
            " the ",
            " a ",
            " an ",
            " is ",
            " are ",
            " was ",
            " were ",
        ]
        has_sentence_indicators = any(
            indicator in value.lower() for indicator in sentence_indicators
        )

        # If it doesn't look like a sentence and has commas, might be an array
        if not has_sentence_indicators:
            return True

    return False


def process_entity_data_for_parsing(data: dict[str, Any]) -> dict[str, Any]:
    """
    Process entity data by applying automatic parsing to all values.

    This function applies generic parsing (date, numeric, array) to all values
    in the dictionary without field-name-based inference.

    Args:
        data: Dictionary containing entity data

    Returns:
        Dictionary with parsed values
    """
    if not isinstance(data, dict):
        return data

    processed_data = {}

    for key, value in data.items():
        try:
            # Skip lock fields and other special fields
            if key.startswith("__") and key.endswith("__lock__"):
                processed_data[key] = value
                continue

            # Apply automatic parsing
            parsed_value = try_parse_value_auto(value)
            processed_data[key] = parsed_value

        except Exception as e:
            logger.warning(f"Failed to parse field '{key}' with value '{value}': {e}")
            # Keep original value on error
            processed_data[key] = value

    return processed_data
