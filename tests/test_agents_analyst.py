"""Tests for app/agents/analyst_agent.py — AnalystAgent and bucketing.

All Gemini calls are mocked; no network access occurs.  The golden suite drives
the success / empty / failed branches from JSON fixtures, with targeted unit
tests covering weekly bucketing, the insight cap, and malformed-output paths.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.analyst_agent import (
    MIN_ACTIVITIES_FOR_INSIGHTS,
    AnalystAgent,
    AnalystEmpty,
    AnalystFailed,
    AnalystSuccess,
    bucket_by_week,
)
from app.models.activity import Activity

_GOLDEN_DIR = Path(__file__).parent / "fixtures" / "agent_goldens" / "analyst"
_GOLDENS = sorted(_GOLDEN_DIR.glob("*.json"))
_FIXED_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _activity(spec: dict[str, Any], now: datetime) -> Activity:
    return Activity(
        id=spec["id"],
        user_id="user-1",
        type=spec["type"],
        timestamp=now - timedelta(days=spec.get("days_ago", 1)),
        raw_input=spec["raw_input"],
        structured_data=spec.get("structured_data", {}),
        emission_kg_co2e=spec["emission_kg_co2e"],
        confidence=spec.get("confidence", "medium"),
        emission_factor_source=spec.get("source", "TEST 2024"),
        agent_reasoning=None,
    )


def _make_model(mock: dict[str, Any]) -> MagicMock:
    model = MagicMock()
    model.model_name = "models/gemini-2.5-pro"
    kind = mock["kind"]
    if kind == "skip":
        model.generate_content_async = AsyncMock(
            side_effect=AssertionError("model must not be called"),
        )
    elif kind == "raise":
        exc_type = {"TimeoutError": TimeoutError, "RuntimeError": RuntimeError}[mock["exception"]]
        model.generate_content_async = AsyncMock(side_effect=exc_type())
    elif kind == "raw":
        model.generate_content_async = AsyncMock(return_value=SimpleNamespace(text=mock["text"]))
    else:
        model.generate_content_async = AsyncMock(
            return_value=SimpleNamespace(text=json.dumps(mock["payload"])),
        )
    return model


def _make_agent(mock: dict[str, Any]) -> tuple[AnalystAgent, MagicMock]:
    model = _make_model(mock)
    factory = MagicMock()
    factory.pro.return_value = model
    return AnalystAgent(gemini_factory=factory), model


@pytest.mark.parametrize("path", _GOLDENS, ids=lambda p: p.stem)
async def test_analyst_golden(path: Path) -> None:
    case = _load(path)
    activities = [_activity(spec, _FIXED_NOW) for spec in case["activities"]]
    agent, model = _make_agent(case["mock"])
    outcome = await agent.generate_insights(
        activities=activities,
        user_id="user-1",
        now=_FIXED_NOW,
    )
    expect = case["expect"]
    assert outcome.status == expect["status"]

    if expect.get("no_model_call"):
        model.generate_content_async.assert_not_called()

    if expect["status"] == "success":
        assert isinstance(outcome, AnalystSuccess)
        assert len(outcome.insights) == expect["insight_count"]
        valid_ids = {activity.id for activity in activities}
        seen_ids: set[str] = set()
        for insight in outcome.insights:
            assert insight.type in {"pattern", "trend", "milestone"}
            assert set(insight.supporting_activity_ids) <= valid_ids
            assert insight.user_id == "user-1"
            assert insight.generated_at == _FIXED_NOW
            assert len(insight.id) == 32
            assert insight.id not in seen_ids
            seen_ids.add(insight.id)
            reasoning = insight.agent_reasoning
            assert reasoning is not None
            assert reasoning.agent_name == "analyst"
            assert reasoning.prompt_version == "analyst-v1"
            assert reasoning.model == "models/gemini-2.5-pro"
            assert reasoning.reasoning_steps
            assert reasoning.latency_ms >= 0
        for forbidden in expect.get("must_not_contain_ids", []):
            for insight in outcome.insights:
                assert forbidden not in insight.supporting_activity_ids
    elif expect["status"] == "empty":
        assert isinstance(outcome, AnalystEmpty)
        assert outcome.reason
        assert outcome.agent_reasoning.agent_name == "analyst"
    else:
        assert isinstance(outcome, AnalystFailed)
        assert outcome.reason
        assert outcome.agent_reasoning.agent_name == "analyst"


def test_bucketing_boundaries() -> None:
    def act(days: int, aid: str) -> Activity:
        spec = {
            "id": aid,
            "type": "food",
            "emission_kg_co2e": 0.9,
            "raw_input": "veg thali",
            "days_ago": days,
        }
        return _activity(spec, _FIXED_NOW)

    activities = [act(0, "d0"), act(6, "d6"), act(7, "d7"), act(13, "d13"), act(14, "d14")]
    buckets = bucket_by_week(activities, now=_FIXED_NOW)
    ids = {key: [activity.id for activity in value] for key, value in buckets.items()}

    assert "d0" in ids["this_week"]
    assert "d6" in ids["this_week"]
    assert "d7" in ids["last_week"]
    assert "d13" in ids["last_week"]
    assert "d14" in ids["earlier"]
    assert "d7" not in ids["this_week"]


async def test_low_data_returns_empty_without_model_call() -> None:
    agent, model = _make_agent({"kind": "skip"})
    activities = [
        _activity(
            {"id": "a1", "type": "food", "emission_kg_co2e": 0.9, "raw_input": "veg thali"},
            _FIXED_NOW,
        )
    ]
    outcome = await agent.generate_insights(activities=activities, user_id="u", now=_FIXED_NOW)
    assert isinstance(outcome, AnalystEmpty)
    assert str(MIN_ACTIVITIES_FOR_INSIGHTS) in outcome.reason
    model.generate_content_async.assert_not_called()


async def test_insights_capped_at_three() -> None:
    activities = [
        _activity(
            {
                "id": f"a{i}",
                "type": "food",
                "emission_kg_co2e": 0.9,
                "raw_input": "veg thali",
                "days_ago": i,
            },
            _FIXED_NOW,
        )
        for i in range(1, 5)
    ]
    payload = {
        "insights": [
            {
                "type": "pattern",
                "title": f"Pattern {i}",
                "description": "A recurring behaviour.",
                "supporting_activity_ids": [f"a{i}"],
            }
            for i in range(1, 5)
        ]
    }
    agent, _ = _make_agent({"kind": "json", "payload": payload})
    outcome = await agent.generate_insights(activities=activities, user_id="u", now=_FIXED_NOW)
    assert isinstance(outcome, AnalystSuccess)
    assert len(outcome.insights) == 3


@pytest.mark.parametrize("text", ["not json at all", '{"x": 1}', '{"insights": 5}'])
async def test_analyst_malformed_shapes_fail(text: str) -> None:
    activities = [
        _activity(
            {
                "id": f"a{i}",
                "type": "food",
                "emission_kg_co2e": 0.9,
                "raw_input": "veg thali",
                "days_ago": i,
            },
            _FIXED_NOW,
        )
        for i in range(1, 4)
    ]
    agent, _ = _make_agent({"kind": "raw", "text": text})
    outcome = await agent.generate_insights(activities=activities, user_id="u", now=_FIXED_NOW)
    assert isinstance(outcome, AnalystFailed)


async def test_analyst_generic_model_error_fails() -> None:
    activities = [
        _activity(
            {
                "id": f"a{i}",
                "type": "food",
                "emission_kg_co2e": 0.9,
                "raw_input": "veg thali",
                "days_ago": i,
            },
            _FIXED_NOW,
        )
        for i in range(1, 4)
    ]
    agent, _ = _make_agent({"kind": "raise", "exception": "RuntimeError"})
    outcome = await agent.generate_insights(activities=activities, user_id="u", now=_FIXED_NOW)
    assert isinstance(outcome, AnalystFailed)
    assert "failed" in outcome.reason.lower()
