"""Tests for app/services/staleness.py — is_pipeline_stale branch coverage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from unittest.mock import AsyncMock

from app.models.activity import Activity
from app.models.generation_state import GenerationState
from app.services.staleness import is_pipeline_stale

_UID = "user-123"
# 2026-06-20 12:00 UTC == 2026-06-20 17:30 IST.
_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


def _state(
    *,
    last_completed_at: datetime,
    analyst_status: Literal["success", "empty", "failed"] = "success",
    coach_status: Literal["success", "empty", "failed", "skipped"] = "success",
) -> GenerationState:
    return GenerationState(
        uid=_UID,
        last_completed_at=last_completed_at,
        analyst_status=analyst_status,
        coach_status=coach_status,
    )


def _activity(timestamp: datetime) -> Activity:
    return Activity(
        id="a1",
        user_id=_UID,
        type="transport",
        timestamp=timestamp,
        raw_input="metro to work",
        structured_data={},
        emission_kg_co2e=1.0,
        confidence="high",
        emission_factor_source="TEST 2024",
    )


async def test_no_prior_run_is_stale(firestore_service_mock: AsyncMock) -> None:
    firestore_service_mock.get_generation_state.return_value = None

    result = await is_pipeline_stale(uid=_UID, firestore=firestore_service_mock, now_utc=_NOW)

    assert result.stale is True
    assert result.reason == "no_prior_run"
    assert result.cached_state is None


async def test_ist_day_change_is_stale(firestore_service_mock: AsyncMock) -> None:
    # now is 2026-06-21 00:30 IST; last run was 2026-06-20 17:30 IST — different
    # IST day despite sharing the same UTC calendar date.
    now_utc = datetime(2026, 6, 20, 19, 0, tzinfo=UTC)
    state = _state(last_completed_at=datetime(2026, 6, 20, 12, 0, tzinfo=UTC))
    firestore_service_mock.get_generation_state.return_value = state

    result = await is_pipeline_stale(uid=_UID, firestore=firestore_service_mock, now_utc=now_utc)

    assert result.stale is True
    assert result.reason == "ist_day_change"
    assert result.cached_state == state


async def test_new_activity_since_last_run_is_stale(firestore_service_mock: AsyncMock) -> None:
    firestore_service_mock.get_generation_state.return_value = _state(
        last_completed_at=datetime(2026, 6, 20, 10, 0, tzinfo=UTC)
    )
    firestore_service_mock.list_activities.return_value = [
        _activity(datetime(2026, 6, 20, 11, 0, tzinfo=UTC))
    ]

    result = await is_pipeline_stale(uid=_UID, firestore=firestore_service_mock, now_utc=_NOW)

    assert result.stale is True
    assert result.reason == "new_activity_since_last_run"


async def test_analyst_empty_ttl_expired_is_stale(firestore_service_mock: AsyncMock) -> None:
    firestore_service_mock.get_generation_state.return_value = _state(
        last_completed_at=datetime(2026, 6, 20, 11, 0, tzinfo=UTC),
        analyst_status="empty",
        coach_status="skipped",
    )
    firestore_service_mock.list_activities.return_value = []

    result = await is_pipeline_stale(uid=_UID, firestore=firestore_service_mock, now_utc=_NOW)

    assert result.stale is True
    assert result.reason == "analyst_empty_ttl_expired"


async def test_coach_empty_ttl_expired_is_stale(firestore_service_mock: AsyncMock) -> None:
    firestore_service_mock.get_generation_state.return_value = _state(
        last_completed_at=datetime(2026, 6, 20, 11, 0, tzinfo=UTC),
        analyst_status="success",
        coach_status="empty",
    )
    firestore_service_mock.list_activities.return_value = []

    result = await is_pipeline_stale(uid=_UID, firestore=firestore_service_mock, now_utc=_NOW)

    assert result.stale is True
    assert result.reason == "coach_empty_ttl_expired"


async def test_empty_within_ttl_is_fresh(firestore_service_mock: AsyncMock) -> None:
    firestore_service_mock.get_generation_state.return_value = _state(
        last_completed_at=datetime(2026, 6, 20, 11, 55, tzinfo=UTC),
        analyst_status="empty",
        coach_status="skipped",
    )
    firestore_service_mock.list_activities.return_value = []

    result = await is_pipeline_stale(uid=_UID, firestore=firestore_service_mock, now_utc=_NOW)

    assert result.stale is False
    assert result.reason == "fresh"


async def test_success_same_day_no_new_activity_is_fresh(
    firestore_service_mock: AsyncMock,
) -> None:
    firestore_service_mock.get_generation_state.return_value = _state(
        last_completed_at=datetime(2026, 6, 20, 10, 0, tzinfo=UTC)
    )
    # Latest activity predates the last run — not newer.
    firestore_service_mock.list_activities.return_value = [
        _activity(datetime(2026, 6, 20, 9, 0, tzinfo=UTC))
    ]

    result = await is_pipeline_stale(uid=_UID, firestore=firestore_service_mock, now_utc=_NOW)

    assert result.stale is False
    assert result.reason == "fresh"
