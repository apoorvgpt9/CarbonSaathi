"""Shared pytest fixtures for the CarbonSaathi test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.auth import CurrentUser, verify_firebase_token
from app.core.config import get_settings
from app.services.firestore_service import FirestoreService, get_firestore_service


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


@pytest.fixture
def firestore_service_mock() -> AsyncMock:
    """Return an ``AsyncMock`` standing in for :class:`FirestoreService`."""
    return AsyncMock(spec=FirestoreService)


@pytest.fixture
def current_user() -> CurrentUser:
    """Return the canonical authenticated user used by route tests."""
    return CurrentUser(
        uid="user-123",
        email="test@example.com",
        email_verified=True,
        name="Test User",
    )


@pytest.fixture
async def client_with_user(
    firestore_service_mock: AsyncMock,
    current_user: CurrentUser,
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield an ASGI client with auth and Firestore dependencies overridden.

    The ``verify_firebase_token`` dependency is replaced with one returning
    ``current_user`` and ``get_firestore_service`` with one returning
    ``firestore_service_mock``.  All overrides are cleared on teardown.
    """
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[verify_firebase_token] = lambda: current_user
    app.dependency_overrides[get_firestore_service] = lambda: firestore_service_mock
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
