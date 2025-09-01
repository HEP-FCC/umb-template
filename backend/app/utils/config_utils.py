"""
Configuration utilities for the Universal Metadata Browser application.

This module provides configuration loading and management functionality
using pyhocon for configuration file parsing.
"""

from pathlib import Path
from typing import cast

from pyhocon import ConfigFactory, ConfigTree

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.conf"


class Config(ConfigTree):  # type: ignore
    """Extended configuration class with type hints."""

    pass


def get_config_from_default_location() -> Config:
    """Load configuration from the default location."""
    if not DEFAULT_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Default configuration file not found at {DEFAULT_CONFIG_PATH}"
        )

    return cast(Config, ConfigFactory.parse_file(str(DEFAULT_CONFIG_PATH)))


def get_config(path: str | None = None) -> Config:
    """
    Load configuration from the specified path or default location.

    Args:
        path: Optional path to a configuration file

    Returns:
        Loaded configuration as a ConfigTree
    """
    if path:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at {path}")
        return cast(Config, ConfigFactory.parse_file(str(config_path)))
    else:
        return get_config_from_default_location()
