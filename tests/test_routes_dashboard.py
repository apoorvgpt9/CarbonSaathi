"""Tests for GET /api/dashboard route."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from freezegun import freeze_time

from app.core.auth import verify_firebase_token
from app.models.activity import Activity
from app.services.firestore_service import get_firestore_service

# Frozen "now" for all time-sensitive tests.
# 2026-06-20T10:00:00Z = 2026-06-20T15:30:00+05:30 IST
# → today_ist = 2026-06-20, week window: 2026-06-14 … 2026-06-20
_FROZEN_UTC = "2026-06-20T10:00:00+00:00"
_UID = "user-123"

# Activity timestamps that fall on known IST calendar days
# (frozen "now" = 2026-06-20T10:00:00Z):
#   2026-06-20T05:00Z = 2026-06-20T10:30 IST  → today_ist     (2026-06-20)
#   2026-06-19T05:00Z = 2026-06-19T10:30 IST  → yesterday_ist (2026-06-19)
#   2026-06-18T05:00Z = 2026-06-18T10:30 IST  → day-before    (2026-06-18)
_TODAY_UTC = datetime(2026, 6, 20, 5, 0, 0, tzinfo=UTC)
_YESTERDAY_UTC = datetime(2026, 6, 19, 5, 0, 0, tzinfo=UTC)
_DAY_BEFORE_UTC = datetime(2026, 6, 18, 5, 0, 0, tzinfo=UTC)


def _make_activity(
    activity_id: str,
    timestamp: datetime,
    emission: float = 1.0,
    activity_type: str = "transport",
) -> Activity:
    return Activity(
        id=activity_id,
        user_id=_UID,
        type=activity_type,
        timestamp=timestamp,
        raw_input="test activity",
        structured_data={},
        emission_kg_co2e=emission,
        confidence="high",
        emission_factor_source="TEST 2024",
        agent_reasoning=None,
    )


@pytest.fixture
async def client_no_auth_dashboard(
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
# Tests
# ---------------------------------------------------------------------------


async def test_dashboard_empty(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    firestore_service_mock.list_activities_in_range.return_value = []
    firestore_service_mock.list_activities.return_value = []

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    assert resp.status_code == 200
    body = resp.json()
    assert body["today_kg"] == 0.0
    assert body["today_by_type"] == {
        "transport_kg": 0.0,
        "electricity_kg": 0.0,
        "food_kg": 0.0,
    }
    assert body["week_total_kg"] == 0.0
    assert len(body["week_by_day"]) == 7
    assert all(d["total_kg"] == 0.0 for d in body["week_by_day"])
    assert body["streak_days"] == 0
    assert body["lifetime_activity_count"] == 0


async def test_dashboard_one_activity_today(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    act = _make_activity("a1", _TODAY_UTC, emission=3.0, activity_type="transport")
    firestore_service_mock.list_activities_in_range.return_value = [act]
    firestore_service_mock.list_activities.return_value = [act]

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    assert resp.status_code == 200
    body = resp.json()
    assert body["today_kg"] == 3.0
    assert body["today_by_type"]["transport_kg"] == 3.0
    assert body["today_by_type"]["electricity_kg"] == 0.0
    assert body["today_by_type"]["food_kg"] == 0.0
    assert body["streak_days"] == 1
    assert body["lifetime_activity_count"] == 1


async def test_dashboard_streak_3_consecutive_days_including_today(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    acts = [
        _make_activity("a1", _TODAY_UTC),
        _make_activity("a2", _YESTERDAY_UTC),
        _make_activity("a3", _DAY_BEFORE_UTC),
    ]
    firestore_service_mock.list_activities_in_range.return_value = acts
    firestore_service_mock.list_activities.return_value = acts

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    assert resp.json()["streak_days"] == 3


async def test_dashboard_streak_grace_yesterday_and_prior_not_today(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    # Today has no activity — grace: walk backward from yesterday.
    streak_acts = [
        _make_activity("a2", _YESTERDAY_UTC),
        _make_activity("a3", _DAY_BEFORE_UTC),
    ]
    firestore_service_mock.list_activities_in_range.return_value = []
    firestore_service_mock.list_activities.return_value = streak_acts

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    assert resp.json()["streak_days"] == 2


async def test_dashboard_streak_grace_no_streak_gap(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    # Today empty, yesterday empty, day-before-yesterday logged → streak=0.
    streak_acts = [_make_activity("a3", _DAY_BEFORE_UTC)]
    firestore_service_mock.list_activities_in_range.return_value = []
    firestore_service_mock.list_activities.return_value = streak_acts

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    assert resp.json()["streak_days"] == 0


async def test_dashboard_ist_boundary_23_30_ist_yesterday_buckets_yesterday(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    # 2026-06-19T18:00:00Z = 2026-06-19T23:30:00+05:30 → IST date 2026-06-19 (yesterday).
    act_utc = datetime(2026, 6, 19, 18, 0, 0, tzinfo=UTC)
    act = _make_activity("a1", act_utc, emission=2.5)
    firestore_service_mock.list_activities_in_range.return_value = [act]
    firestore_service_mock.list_activities.return_value = [act]

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    body = resp.json()
    assert body["today_kg"] == 0.0  # not bucketed into today
    yesterday_entry = next(d for d in body["week_by_day"] if d["date_ist"] == "2026-06-19")
    assert yesterday_entry["total_kg"] == 2.5


async def test_dashboard_ist_boundary_00_30_ist_today_buckets_today(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    # 2026-06-19T19:00:00Z = 2026-06-20T00:30:00+05:30 → IST date 2026-06-20 (today).
    act_utc = datetime(2026, 6, 19, 19, 0, 0, tzinfo=UTC)
    act = _make_activity("a1", act_utc, emission=1.5)
    firestore_service_mock.list_activities_in_range.return_value = [act]
    firestore_service_mock.list_activities.return_value = [act]

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    body = resp.json()
    assert body["today_kg"] == 1.5  # bucketed into today


async def test_dashboard_mixed_types_by_type_breakdown(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    acts = [
        _make_activity("a1", _TODAY_UTC, emission=1.0, activity_type="transport"),
        _make_activity("a2", _TODAY_UTC, emission=2.0, activity_type="electricity"),
        _make_activity("a3", _TODAY_UTC, emission=0.5, activity_type="food"),
    ]
    firestore_service_mock.list_activities_in_range.return_value = acts
    firestore_service_mock.list_activities.return_value = acts

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    body = resp.json()
    assert body["today_kg"] == 3.5
    assert body["today_by_type"]["transport_kg"] == 1.0
    assert body["today_by_type"]["electricity_kg"] == 2.0
    assert body["today_by_type"]["food_kg"] == 0.5


async def test_dashboard_week_by_day_7_entries_oldest_first(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
) -> None:
    act = _make_activity("a1", _TODAY_UTC, emission=1.0)
    firestore_service_mock.list_activities_in_range.return_value = [act]
    firestore_service_mock.list_activities.return_value = [act]

    with freeze_time(_FROZEN_UTC):
        resp = await client_with_user.get("/api/dashboard")

    body = resp.json()
    days = body["week_by_day"]
    assert len(days) == 7
    # Oldest entry (index 0): today - 6 days = 2026-06-14
    assert days[0]["date_ist"] == "2026-06-14"
    # Newest entry (index 6): today = 2026-06-20
    assert days[6]["date_ist"] == "2026-06-20"
    # Only today (index 6) has emission; all prior days are zero.
    assert days[6]["total_kg"] == 1.0
    assert all(d["total_kg"] == 0.0 for d in days[:6])


async def test_dashboard_missing_auth_401(
    client_no_auth_dashboard: httpx.AsyncClient,
) -> None:
    resp = await client_no_auth_dashboard.get("/api/dashboard")
    assert resp.status_code == 401
