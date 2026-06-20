"""Tests for app/routes/recommendations.py — list + accept mutation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.auth import verify_firebase_token
from app.models.recommendation import Recommendation
from app.services.firestore_service import get_firestore_service

_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


def _rec() -> Recommendation:
    return Recommendation(
        id="r1",
        user_id="user-123",
        generated_at=_NOW,
        type="swap",
        title="Use the metro",
        description="Switch your commute to the metro.",
        expected_saving_kg=1.0,
        difficulty="easy",
        accepted=False,
    )


@pytest.fixture
async def client_no_auth_recommendations(
    firestore_service_mock: AsyncMock,
) -> AsyncIterator[httpx.AsyncClient]:
    """Client with Firestore mocked but auth overridden to raise 401."""
    from fastapi import HTTPException

    from app.main import create_app

    app = create_app()

    def _raise_401() -> None:
        raise HTTPException(status_code=401, detail="Authentication failed")

    app.dependency_overrides[verify_firebase_token] = _raise_401
    app.dependency_overrides[get_firestore_service] = lambda: firestore_service_mock
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/recommendations (read-only)
# ---------------------------------------------------------------------------


async def test_list_recommendations_returns_items(
    client_with_user: httpx.AsyncClient, firestore_service_mock: AsyncMock
) -> None:
    firestore_service_mock.get_recent_recommendations.return_value = [_rec()]

    resp = await client_with_user.get("/api/recommendations")

    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


async def test_list_recommendations_empty_is_200(
    client_with_user: httpx.AsyncClient, firestore_service_mock: AsyncMock
) -> None:
    firestore_service_mock.get_recent_recommendations.return_value = []

    resp = await client_with_user.get("/api/recommendations")

    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_list_recommendations_requires_auth(
    client_no_auth_recommendations: httpx.AsyncClient,
) -> None:
    resp = await client_no_auth_recommendations.get("/api/recommendations")

    assert resp.status_code == 401
    assert int(resp.headers["content-length"]) == 34
    assert resp.json() == {"detail": "Authentication failed"}


# ---------------------------------------------------------------------------
# POST /api/recommendations/{rec_id}/accept
# ---------------------------------------------------------------------------


async def test_accept_recommendation_success(
    client_with_user: httpx.AsyncClient, firestore_service_mock: AsyncMock
) -> None:
    firestore_service_mock.accept_recommendation.return_value = True

    resp = await client_with_user.post("/api/recommendations/r1/accept")

    assert resp.status_code == 200
    assert resp.json() == {"accepted": True, "rec_id": "r1"}
    firestore_service_mock.accept_recommendation.assert_awaited_once_with("user-123", "r1")


async def test_accept_recommendation_not_found(
    client_with_user: httpx.AsyncClient, firestore_service_mock: AsyncMock
) -> None:
    firestore_service_mock.accept_recommendation.return_value = False

    resp = await client_with_user.post("/api/recommendations/ghost/accept")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Recommendation not found"}


async def test_accept_recommendation_other_user_is_404(
    client_with_user: httpx.AsyncClient, firestore_service_mock: AsyncMock
) -> None:
    # A rec owned by another user is not present under this user's path, so the
    # service returns False — identical 404 to "not found", no ownership leak.
    firestore_service_mock.accept_recommendation.return_value = False

    resp = await client_with_user.post("/api/recommendations/someone-elses-rec/accept")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Recommendation not found"}


async def test_accept_recommendation_requires_auth(
    client_no_auth_recommendations: httpx.AsyncClient,
) -> None:
    resp = await client_no_auth_recommendations.post("/api/recommendations/r1/accept")

    assert resp.status_code == 401
    assert int(resp.headers["content-length"]) == 34
    assert resp.json() == {"detail": "Authentication failed"}
