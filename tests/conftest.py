"""Shared pytest fixtures for the CarbonSaathi test suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide required environment variables and reset the settings cache.

    Runs automatically before every test so that ``get_settings()`` constructs
    a fresh, fully populated ``Settings`` instance.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "test-project")
    monkeypatch.setenv("FIREBASE_API_KEY", "test-fb-api-key")
    monkeypatch.setenv("FIREBASE_AUTH_DOMAIN", "test.firebaseapp.com")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
