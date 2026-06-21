"""Tests for app/core/ratelimit.py — per-user rate limiting (Phase 7 B2).

The conftest fixture disables ``limiter.enabled`` for the whole session so
the bulk suite is not affected by accumulated counts; this module re-enables
the limiter under an autouse fixture and resets its in-memory storage
between tests so each test starts from an empty bucket.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import Request

from app.core.auth import CurrentUser, verify_firebase_token
from app.core.ratelimit import key_uid_or_ip, limiter
from app.services.firestore_service import get_firestore_service


@pytest.fixture(autouse=True)
def _enable_limiter_for_module() -> Iterator[None]:
    """Re-enable the limiter for tests in this module and reset between tests."""
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


# ---------------------------------------------------------------------------
# Unit tests for key_uid_or_ip
# ---------------------------------------------------------------------------


def test_key_uid_or_ip_uses_uid_when_user_attached() -> None:
    """When ``request.state.user`` is set, the key is ``uid:<uid>``."""
    request = MagicMock()
    request.state = SimpleNamespace(user=CurrentUser(uid="alice-uid"))
    assert key_uid_or_ip(request) == "uid:alice-uid"


def test_key_uid_or_ip_falls_back_to_ip_when_no_user() -> None:
    """Without ``request.state.user`` we fall back to the client's IP."""
    request = MagicMock()
    request.state = SimpleNamespace()
    request.client = SimpleNamespace(host="203.0.113.7")
    request.headers = {}
    assert key_uid_or_ip(request) == "ip:203.0.113.7"


# ---------------------------------------------------------------------------
# Integration tests against the live FastAPI app
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(
    firestore_service_mock: AsyncMock,
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a test client whose auth dependency reads ``X-Test-Uid``.

    Each request can therefore pretend to be any user, which is what makes
    "different uids get independent buckets" testable.
    """
    from app.main import create_app

    firestore_service_mock.accept_recommendation.return_value = True

    app = create_app()

    def _auth_override(request: Request) -> CurrentUser:
        uid = request.headers.get("X-Test-Uid", "default-uid")
        user = CurrentUser(uid=uid)
        request.state.user = user
        return user

    app.dependency_overrides[verify_firebase_token] = _auth_override
    app.dependency_overrides[get_firestore_service] = lambda: firestore_service_mock

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_per_uid_bucket_is_enforced(client: httpx.AsyncClient) -> None:
    """The first 30 POSTs on ``/api/recommendations/{id}/accept`` succeed;
    the 31st (same uid) is rejected with HTTP 429."""
    path = "/api/recommendations/rec-1/accept"
    headers = {"X-Test-Uid": "uid-a"}
    for i in range(30):
        resp = await client.post(path, headers=headers)
        assert resp.status_code == 200, f"call {i + 1} should succeed, got {resp.status_code}"
    over = await client.post(path, headers=headers)
    assert over.status_code == 429
    assert over.json() == {"detail": "Rate limit exceeded"}


@pytest.mark.asyncio
async def test_different_uids_have_independent_buckets(
    client: httpx.AsyncClient,
) -> None:
    """After ``uid-a`` exhausts its 30/minute budget, ``uid-b`` still goes
    through — the bucket is keyed on the uid, not on shared IP."""
    path = "/api/recommendations/rec-1/accept"
    for _ in range(30):
        resp = await client.post(path, headers={"X-Test-Uid": "uid-a"})
        assert resp.status_code == 200
    blocked = await client.post(path, headers={"X-Test-Uid": "uid-a"})
    assert blocked.status_code == 429

    other = await client.post(path, headers={"X-Test-Uid": "uid-b"})
    assert other.status_code == 200, f"uid-b should have its own bucket but got {other.status_code}"
