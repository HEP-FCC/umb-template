"""
Logging utilities for the Universal Metadata Browser application.

This module provides a structured logging setup using structlog,
with proper configuration and type hints.
"""

import logging
from logging import Logger
from typing import cast

import structlog

from app.utils.config_utils import get_config

config = get_config()
LOG_LEVEL = config.get("general.log_level", "INFO").strip().upper()

# Flag to track if logging has been configured
_logging_configured = False


def setup_logging() -> None:
    """
    Set up structured logging for the application.
    This should be called once at application startup.
    """
    global _logging_configured

    # Avoid reconfiguring if already set up
    if _logging_configured:
        return

    # Get the root logger and completely clear it
    root_logger = logging.getLogger()

    # Clear ALL handlers to ensure no duplicates
    root_logger.handlers.clear()

    # Set the level
    root_logger.setLevel(LOG_LEVEL)

    # Clear any existing structlog configuration
    structlog.reset_defaults()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Add handler to root logger
    handler = logging.StreamHandler()
    handler.setLevel(LOG_LEVEL)
    root_logger.addHandler(handler)

    _logging_configured = True


def get_logger(name: str | None = None) -> Logger:
    """
    Get a logger instance for the given name.

    Args:
        name: Logger name, typically __name__ from the calling module

    Returns:
        Configured logger instance
    """
    # Ensure logging is set up
    if not _logging_configured:
        setup_logging()

    # Get the logger and ensure it's typed correctly
    logger = structlog.stdlib.get_logger(name)
    return cast(Logger, logger)
