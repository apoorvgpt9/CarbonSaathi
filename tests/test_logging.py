"""Tests for logging configuration."""

from __future__ import annotations

import pytest
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging


def test_configure_logging_succeeds() -> None:
    configure_logging()


def test_get_logger_returns_bound_logger() -> None:
    configure_logging()
    logger = structlog.get_logger("test")
    logger.info("test")


def test_configure_logging_json_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    configure_logging()
    structlog.get_logger("prod").info("prod-event")
