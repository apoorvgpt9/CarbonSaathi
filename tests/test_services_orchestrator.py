"""Tests for app/services/orchestrator.py — run_insight_pipeline flows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from unittest.mock import AsyncMock

import pytest

import app.services.orchestrator as orchestrator
from app.agents.analyst_agent import AnalystEmpty, AnalystFailed, AnalystSuccess
from app.agents.coach_agent import CoachEmpty, CoachFailed, CoachSuccess
from app.models.activity import Activity
from app.models.generation_state import GenerationState
from app.models.insight import Insight
from app.models.recommendation import Recommendation
from app.models.shared import AgentReasoning
from app.models.user import HomeProfile, IndianState, UserProfile
from app.services.orchestrator import (
    Done,
    PhaseComplete,
    PhaseStart,
    ReasoningStep,
    run_insight_pipeline,
)
from app.services.staleness import StalenessResult

_UID = "user-123"
_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _reasoning(agent: Literal["logger", "analyst", "coach"], steps: list[str]) -> AgentReasoning:
    return AgentReasoning(
        agent_name=agent,
        prompt_version="v1",
        input_summary="in",
        reasoning_steps=steps,
        output_summary="out",
        model="gemini-2.5-pro",
        latency_ms=5,
    )


def _insight(steps: list[str] | None = None, *, with_reasoning: bool = True) -> Insight:
    return Insight(
        id="i1",
        user_id=_UID,
        generated_at=_NOW,
        type="pattern",
        title="Title",
        description="Description",
        supporting_activity_ids=[],
        agent_reasoning=_reasoning("analyst", steps or []) if with_reasoning else None,
    )


def _recommendation(
    steps: list[str] | None = None, *, with_reasoning: bool = True
) -> Recommendation:
    return Recommendation(
        id="r1",
        user_id=_UID,
        generated_at=_NOW,
        type="swap",
        title="Title",
        description="Description",
        expected_saving_kg=1.0,
        difficulty="easy",
        accepted=False,
        agent_reasoning=_reasoning("coach", steps or []) if with_reasoning else None,
    )


def _profile() -> UserProfile:
    return UserProfile(
        uid=_UID,
        email="test@example.com",
        display_name="Test",
        state=IndianState.MAHARASHTRA,
        home_profile=HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="veg"),
        created_at=_NOW,
        last_active=_NOW,
        onboarding_complete=True,
    )


def _activity() -> Activity:
    return Activity(
        id="a1",
        user_id=_UID,
        type="transport",
        timestamp=_NOW,
        raw_input="metro to work",
        structured_data={},
        emission_kg_co2e=1.0,
        confidence="high",
        emission_factor_source="TEST 2024",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_stale(
    monkeypatch: pytest.MonkeyPatch, *, stale: bool, cached_state: GenerationState | None = None
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "is_pipeline_stale",
        AsyncMock(
            return_value=StalenessResult(
                stale=stale, reason="x" if stale else "fresh", cached_state=cached_state
            )
        ),
    )


def _summary(events: list[Any]) -> list[Any]:
    rows: list[Any] = []
    for event in events:
        if isinstance(event, PhaseStart):
            rows.append(("phase_start", event.phase))
        elif isinstance(event, ReasoningStep):
            rows.append(("reasoning", event.phase, event.step))
        elif isinstance(event, PhaseComplete):
            rows.append(("phase_complete", event.phase, event.status))
        else:
            rows.append(("done", event.analyst_status, event.coach_status))
    return rows


def _serialized(events: list[Any]) -> str:
    return " ".join(json.dumps(e.model_dump(mode="json")) for e in events)


async def _drain(
    analyst: AsyncMock, coach: AsyncMock, firestore: AsyncMock, *, pass_now: bool = True
) -> list[Any]:
    if pass_now:
        gen = run_insight_pipeline(
            uid=_UID,
            profile=_profile(),
            analyst=analyst,
            coach=coach,
            firestore=firestore,
            now=_NOW,
        )
    else:
        gen = run_insight_pipeline(
            uid=_UID, profile=_profile(), analyst=analyst, coach=coach, firestore=firestore
        )
    return [event async for event in gen]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_cached_path_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
    firestore_service_mock: AsyncMock,
    analyst_agent_mock: AsyncMock,
    coach_agent_mock: AsyncMock,
) -> None:
    _patch_stale(monkeypatch, stale=False)
    insight = _insight(["a1"])
    rec = _recommendation(["c1"])
    firestore_service_mock.get_recent_insights.return_value = [insight]
    firestore_service_mock.get_recent_recommendations.return_value = [rec]

    # Omit `now` to exercise the default-timestamp branch.
    events = await _drain(
        analyst_agent_mock, coach_agent_mock, firestore_service_mock, pass_now=False
    )

    assert _summary(events) == [
        ("phase_complete", "analyst", "cached"),
        ("phase_complete", "coach", "cached"),
        ("done", "cached", "cached"),
    ]
    done = events[-1]
    assert isinstance(done, Done)
    assert done.insights == [insight]
    assert done.recommendations == [rec]
    analyst_agent_mock.generate_insights.assert_not_called()
    coach_agent_mock.generate_recommendations.assert_not_called()
    firestore_service_mock.set_generation_state.assert_not_called()


async def test_analyst_success_coach_success(
    monkeypatch: pytest.MonkeyPatch,
    firestore_service_mock: AsyncMock,
    analyst_agent_mock: AsyncMock,
    coach_agent_mock: AsyncMock,
) -> None:
    _patch_stale(monkeypatch, stale=True)
    firestore_service_mock.list_activities_in_range.return_value = [_activity()]
    insight = _insight(["a1", "a2"])
    rec = _recommendation(["c1", "c2"])
    analyst_agent_mock.generate_insights.return_value = AnalystSuccess(insights=[insight])
    coach_agent_mock.generate_recommendations.return_value = CoachSuccess(recommendations=[rec])

    events = await _drain(analyst_agent_mock, coach_agent_mock, firestore_service_mock)

    assert _summary(events) == [
        ("phase_start", "analyst"),
        ("reasoning", "analyst", "a1"),
        ("reasoning", "analyst", "a2"),
        ("phase_complete", "analyst", "success"),
        ("phase_start", "coach"),
        ("reasoning", "coach", "c1"),
        ("reasoning", "coach", "c2"),
        ("phase_complete", "coach", "success"),
        ("done", "success", "success"),
    ]
    firestore_service_mock.add_insight.assert_awaited_once_with(insight)
    firestore_service_mock.add_recommendation.assert_awaited_once_with(rec)
    firestore_service_mock.set_generation_state.assert_awaited_once()
    state = firestore_service_mock.set_generation_state.await_args.args[1]
    assert state.analyst_status == "success"
    assert state.coach_status == "success"
    assert state.last_completed_at == _NOW
    done = events[-1]
    assert isinstance(done, Done)
    assert done.insights == [insight]
    assert done.recommendations == [rec]


async def test_analyst_empty_skips_coach(
    monkeypatch: pytest.MonkeyPatch,
    firestore_service_mock: AsyncMock,
    analyst_agent_mock: AsyncMock,
    coach_agent_mock: AsyncMock,
) -> None:
    _patch_stale(monkeypatch, stale=True)
    firestore_service_mock.list_activities_in_range.return_value = []
    analyst_agent_mock.generate_insights.return_value = AnalystEmpty(
        reason="Log more activities", agent_reasoning=_reasoning("analyst", ["too few"])
    )

    events = await _drain(analyst_agent_mock, coach_agent_mock, firestore_service_mock)

    assert _summary(events) == [
        ("phase_start", "analyst"),
        ("phase_complete", "analyst", "empty"),
        ("phase_start", "coach"),
        ("phase_complete", "coach", "skipped"),
        ("done", "empty", "skipped"),
    ]
    analyst_complete = next(
        e for e in events if isinstance(e, PhaseComplete) and e.phase == "analyst"
    )
    assert analyst_complete.reason == "Log more activities"
    coach_complete = next(e for e in events if isinstance(e, PhaseComplete) and e.phase == "coach")
    assert coach_complete.reason == "Insufficient insight data"
    coach_agent_mock.generate_recommendations.assert_not_called()
    firestore_service_mock.add_insight.assert_not_awaited()
    state = firestore_service_mock.set_generation_state.await_args.args[1]
    assert state.analyst_status == "empty"
    assert state.coach_status == "skipped"
    assert state.empty_reason == "Log more activities"
    done = events[-1]
    assert isinstance(done, Done)
    assert done.insights == []
    assert done.recommendations == []


async def test_analyst_failed_uses_safe_message(
    monkeypatch: pytest.MonkeyPatch,
    firestore_service_mock: AsyncMock,
    analyst_agent_mock: AsyncMock,
    coach_agent_mock: AsyncMock,
) -> None:
    _patch_stale(monkeypatch, stale=True)
    firestore_service_mock.list_activities_in_range.return_value = [_activity()]
    analyst_agent_mock.generate_insights.return_value = AnalystFailed(
        reason="Gemini call failed: secret-stacktrace-xyz",
        agent_reasoning=_reasoning("analyst", ["model error"]),
    )

    events = await _drain(analyst_agent_mock, coach_agent_mock, firestore_service_mock)

    assert _summary(events) == [
        ("phase_start", "analyst"),
        ("phase_complete", "analyst", "failed"),
        ("phase_start", "coach"),
        ("phase_complete", "coach", "skipped"),
        ("done", "failed", "skipped"),
    ]
    analyst_complete = next(
        e for e in events if isinstance(e, PhaseComplete) and e.phase == "analyst"
    )
    assert analyst_complete.reason == "Analyst step could not complete"
    assert "secret-stacktrace-xyz" not in _serialized(events)
    coach_agent_mock.generate_recommendations.assert_not_called()
    state = firestore_service_mock.set_generation_state.await_args.args[1]
    assert state.analyst_status == "failed"
    assert state.coach_status == "skipped"
    assert state.failed_reason == "Analyst step could not complete"


async def test_coach_empty_keeps_insights(
    monkeypatch: pytest.MonkeyPatch,
    firestore_service_mock: AsyncMock,
    analyst_agent_mock: AsyncMock,
    coach_agent_mock: AsyncMock,
) -> None:
    _patch_stale(monkeypatch, stale=True)
    firestore_service_mock.list_activities_in_range.return_value = [_activity()]
    insight = _insight(["a1"])
    analyst_agent_mock.generate_insights.return_value = AnalystSuccess(insights=[insight])
    coach_agent_mock.generate_recommendations.return_value = CoachEmpty(
        reason="Complete onboarding", agent_reasoning=_reasoning("coach", ["not onboarded"])
    )

    events = await _drain(analyst_agent_mock, coach_agent_mock, firestore_service_mock)

    assert _summary(events) == [
        ("phase_start", "analyst"),
        ("reasoning", "analyst", "a1"),
        ("phase_complete", "analyst", "success"),
        ("phase_start", "coach"),
        ("phase_complete", "coach", "empty"),
        ("done", "success", "empty"),
    ]
    firestore_service_mock.add_insight.assert_awaited_once_with(insight)
    firestore_service_mock.add_recommendation.assert_not_awaited()
    state = firestore_service_mock.set_generation_state.await_args.args[1]
    assert state.analyst_status == "success"
    assert state.coach_status == "empty"
    assert state.empty_reason == "Complete onboarding"
    done = events[-1]
    assert isinstance(done, Done)
    assert done.insights == [insight]
    assert done.recommendations == []


async def test_coach_failed_uses_safe_message(
    monkeypatch: pytest.MonkeyPatch,
    firestore_service_mock: AsyncMock,
    analyst_agent_mock: AsyncMock,
    coach_agent_mock: AsyncMock,
) -> None:
    _patch_stale(monkeypatch, stale=True)
    firestore_service_mock.list_activities_in_range.return_value = [_activity()]
    insight = _insight(["a1"])
    analyst_agent_mock.generate_insights.return_value = AnalystSuccess(insights=[insight])
    coach_agent_mock.generate_recommendations.return_value = CoachFailed(
        reason="Gemini call failed: coach-secret-xyz",
        agent_reasoning=_reasoning("coach", ["model error"]),
    )

    events = await _drain(analyst_agent_mock, coach_agent_mock, firestore_service_mock)

    coach_complete = next(e for e in events if isinstance(e, PhaseComplete) and e.phase == "coach")
    assert coach_complete.status == "failed"
    assert coach_complete.reason == "Coach step could not complete"
    assert "coach-secret-xyz" not in _serialized(events)
    firestore_service_mock.add_recommendation.assert_not_awaited()
    state = firestore_service_mock.set_generation_state.await_args.args[1]
    assert state.analyst_status == "success"
    assert state.coach_status == "failed"
    assert state.failed_reason == "Coach step could not complete"
    done = events[-1]
    assert isinstance(done, Done)
    assert done.insights == [insight]
    assert done.recommendations == []


async def test_success_with_empty_item_lists_streams_no_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    firestore_service_mock: AsyncMock,
    analyst_agent_mock: AsyncMock,
    coach_agent_mock: AsyncMock,
) -> None:
    # Defensive: success contract drift yielding empty lists must not index [0].
    _patch_stale(monkeypatch, stale=True)
    firestore_service_mock.list_activities_in_range.return_value = [_activity()]
    analyst_agent_mock.generate_insights.return_value = AnalystSuccess(insights=[])
    coach_agent_mock.generate_recommendations.return_value = CoachSuccess(recommendations=[])

    events = await _drain(analyst_agent_mock, coach_agent_mock, firestore_service_mock)

    assert _summary(events) == [
        ("phase_start", "analyst"),
        ("phase_complete", "analyst", "success"),
        ("phase_start", "coach"),
        ("phase_complete", "coach", "success"),
        ("done", "success", "success"),
    ]
    firestore_service_mock.add_insight.assert_not_awaited()
    firestore_service_mock.add_recommendation.assert_not_awaited()


async def test_success_with_no_reasoning_trace_streams_no_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    firestore_service_mock: AsyncMock,
    analyst_agent_mock: AsyncMock,
    coach_agent_mock: AsyncMock,
) -> None:
    # Defensive: items whose agent_reasoning is None must not crash.
    _patch_stale(monkeypatch, stale=True)
    firestore_service_mock.list_activities_in_range.return_value = [_activity()]
    insight = _insight(with_reasoning=False)
    rec = _recommendation(with_reasoning=False)
    analyst_agent_mock.generate_insights.return_value = AnalystSuccess(insights=[insight])
    coach_agent_mock.generate_recommendations.return_value = CoachSuccess(recommendations=[rec])

    events = await _drain(analyst_agent_mock, coach_agent_mock, firestore_service_mock)

    assert not any(isinstance(e, ReasoningStep) for e in events)
    firestore_service_mock.add_insight.assert_awaited_once_with(insight)
    firestore_service_mock.add_recommendation.assert_awaited_once_with(rec)
