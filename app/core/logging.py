"""Structured logging configuration for CarbonSaathi.

Wires the standard library logging module and ``structlog`` together so that
the application emits human-readable logs in development and JSON logs (suitable
for Cloud Logging) elsewhere.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.typing import Processor

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure standard library logging and ``structlog``.

    The log level and renderer are derived from the application settings. In the
    ``development`` environment a colourised console renderer is used; otherwise
    logs are rendered as JSON for ingestion by Cloud Logging.

    Returns:
        None.
    """
    settings = get_settings()
    level = logging.getLevelNamesMapping()[settings.log_level]

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.app_env == "development":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
