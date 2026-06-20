"""Tests for app/routes/auth.py — POST /api/auth/verify.

Auth and Firestore dependencies are overridden via the ``client_with_user``
fixture; no real Firebase or Firestore access occurs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.core.auth import CurrentUser, verify_firebase_token
from app.models.user import HomeProfile, IndianState, UserProfile
from app.routes.auth import _display_name
from app.services.firestore_service import get_firestore_service


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


def test_display_name_prefers_name() -> None:
    assert _display_name(CurrentUser(uid="u", name="Bob", email="bob@example.com")) == "Bob"


def test_display_name_falls_back_to_email_local_part() -> None:
    assert _display_name(CurrentUser(uid="u", email="bob@example.com")) == "bob"


def test_display_name_defaults_to_user() -> None:
    assert _display_name(CurrentUser(uid="u")) == "User"


async def test_verify_new_user_creates_profile(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    current_user: CurrentUser,
) -> None:
    firestore_service_mock.get_user.return_value = None
    resp = await client_with_user.post("/api/auth/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_new"] is True
    assert body["user"]["uid"] == current_user.uid
    assert body["user"]["state"] is None
    assert body["user"]["onboarding_complete"] is False
    firestore_service_mock.upsert_user.assert_awaited_once()
    saved = firestore_service_mock.upsert_user.await_args.args[0]
    assert saved.uid == current_user.uid
    assert saved.state is None
    assert saved.home_profile is None
    assert saved.onboarding_complete is False
    assert saved.display_name == "Test User"


async def test_verify_existing_user_updates_last_active(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    current_user: CurrentUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firestore_service_mock.get_user.return_value = _profile(current_user.uid, onboarded=True)
    calls: dict[str, int] = {"n": 0}

    def _fake_fire_and_forget(coro: object) -> None:
        coro.close()  # type: ignore[attr-defined]
        calls["n"] += 1

    monkeypatch.setattr("app.routes.auth.fire_and_forget", _fake_fire_and_forget)
    resp = await client_with_user.post("/api/auth/verify")
    assert resp.status_code == 200
    assert resp.json()["is_new"] is False
    assert calls["n"] == 1
    firestore_service_mock.upsert_user.assert_not_awaited()


async def test_verify_unauthorized_propagates_401(
    firestore_service_mock: AsyncMock,
) -> None:
    from app.main import create_app

    app = create_app()

    def _raise() -> CurrentUser:
        raise HTTPException(status_code=401, detail="Authentication failed")

    app.dependency_overrides[verify_firebase_token] = _raise
    app.dependency_overrides[get_firestore_service] = lambda: firestore_service_mock
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post("/api/auth/verify")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Authentication failed"
    finally:
        app.dependency_overrides.clear()
