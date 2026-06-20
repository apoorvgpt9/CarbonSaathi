"""Tests for app/routes/users.py — GET /api/users/me and POST /api/users/onboarding.

Auth and Firestore dependencies are overridden via the ``client_with_user``
fixture; no real Firebase or Firestore access occurs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx

from app.core.auth import CurrentUser
from app.models.user import HomeProfile, IndianState, UserProfile

_VALID_HOME: dict[str, Any] = {
    "bhk": 2,
    "has_ac": True,
    "fridge_class": "3-star",
    "dietary": "veg",
}


def _profile(uid: str, *, onboarded: bool) -> UserProfile:
    now = datetime.now(tz=UTC)
    return UserProfile(
        uid=uid,
        email="test@example.com",
        display_name="Test User",
        state=IndianState.KARNATAKA if onboarded else None,
        home_profile=(
            HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="veg")
            if onboarded
            else None
        ),
        created_at=now,
        last_active=now,
        onboarding_complete=onboarded,
    )


async def test_get_me_success(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    current_user: CurrentUser,
) -> None:
    firestore_service_mock.get_user.return_value = _profile(current_user.uid, onboarded=True)
    resp = await client_with_user.get("/api/users/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["uid"] == current_user.uid
    assert body["onboarding_complete"] is True


async def test_get_me_not_found_404(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    firestore_service_mock.get_user.return_value = None
    resp = await client_with_user.get("/api/users/me")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "User profile not found"


async def test_onboarding_success_sets_complete(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    current_user: CurrentUser,
) -> None:
    firestore_service_mock.get_user.return_value = _profile(current_user.uid, onboarded=False)
    payload = {"state": "Karnataka", "home_profile": _VALID_HOME}
    resp = await client_with_user.post("/api/users/onboarding", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["onboarding_complete"] is True
    assert body["state"] == "Karnataka"
    firestore_service_mock.upsert_user.assert_awaited_once()
    saved = firestore_service_mock.upsert_user.await_args.args[0]
    assert saved.onboarding_complete is True
    assert saved.state == IndianState.KARNATAKA
    assert saved.home_profile is not None


async def test_onboarding_invalid_state_422(
    client_with_user: httpx.AsyncClient,
) -> None:
    payload = {"state": "Wakanda", "home_profile": _VALID_HOME}
    resp = await client_with_user.post("/api/users/onboarding", json=payload)
    assert resp.status_code == 422


async def test_onboarding_user_missing_404(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    firestore_service_mock.get_user.return_value = None
    payload = {"state": "Karnataka", "home_profile": _VALID_HOME}
    resp = await client_with_user.post("/api/users/onboarding", json=payload)
    assert resp.status_code == 404


async def test_onboarding_twice_allowed_200(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    current_user: CurrentUser,
) -> None:
    firestore_service_mock.get_user.return_value = _profile(current_user.uid, onboarded=True)
    payload = {
        "state": "Kerala",
        "home_profile": {
            "bhk": 3,
            "has_ac": False,
            "fridge_class": "4-star",
            "dietary": "non-veg",
        },
    }
    r1 = await client_with_user.post("/api/users/onboarding", json=payload)
    r2 = await client_with_user.post("/api/users/onboarding", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
