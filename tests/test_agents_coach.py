"""Tests for app/agents/coach_agent.py — CoachAgent and saving computation.

All Gemini calls are mocked; no network access occurs.  The golden suite drives
the success / empty / failed branches from JSON fixtures, and the saving figures
are re-derived from the live emission service so the assertions never hard-code
factor values.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import TypeAdapter

from app.agents.coach_agent import (
    CoachAgent,
    CoachEmpty,
    CoachFailed,
    CoachSuccess,
    ElectricityReduceBasis,
    FoodSwapBasis,
    SavingBasis,
    TransportSwapBasis,
    _evaluate_basis,
)
from app.agents.prompts.coach_v1 import build_user_prompt
from app.models.activity import Activity
from app.models.insight import Insight
from app.models.user import HomeProfile, IndianState, UserProfile
from app.services.emission_service import get_emission_service

_GOLDEN_DIR = Path(__file__).parent / "fixtures" / "agent_goldens" / "coach"
_GOLDENS = sorted(_GOLDEN_DIR.glob("*.json"))
_FIXED_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
_SERVICE = get_emission_service()
_BASIS_ADAPTER: TypeAdapter[Any] = TypeAdapter(SavingBasis)


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


def _insight(spec: dict[str, Any], now: datetime) -> Insight:
    return Insight(
        id=f"ins-{spec['title']}",
        user_id="user-1",
        generated_at=now,
        type=spec["type"],
        title=spec["title"],
        description="Context insight.",
        supporting_activity_ids=[],
        agent_reasoning=None,
    )


def _profile(state: str) -> UserProfile:
    return UserProfile(
        uid="user-1",
        email="user@example.com",
        display_name="User",
        state=IndianState(state),
        home_profile=HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="non-veg"),
        created_at=_FIXED_NOW,
        last_active=_FIXED_NOW,
        onboarding_complete=True,
    )


def _make_model(mock: dict[str, Any]) -> MagicMock:
    model = MagicMock()
    model.model_name = "models/gemini-2.5-flash"
    kind = mock["kind"]
    if kind == "raise":
        exc_type = {"TimeoutError": TimeoutError, "RuntimeError": RuntimeError}[mock["exception"]]
        model.generate_content_async = AsyncMock(side_effect=exc_type())
    elif kind == "raw":
        model.generate_content_async = AsyncMock(return_value=SimpleNamespace(text=mock["text"]))
    else:
        model.generate_content_async = AsyncMock(
            return_value=SimpleNamespace(text=json.dumps(mock["payload"])),
        )
    return model


def _make_agent(mock: dict[str, Any]) -> tuple[CoachAgent, MagicMock]:
    model = _make_model(mock)
    factory = MagicMock()
    factory.flash.return_value = model
    return CoachAgent(emission_service=_SERVICE, gemini_factory=factory), model


@pytest.mark.parametrize("path", _GOLDENS, ids=lambda p: p.stem)
async def test_coach_golden(path: Path) -> None:
    case = _load(path)
    state = IndianState(case["user_state"])
    profile = _profile(case["user_state"])
    activities = [_activity(spec, _FIXED_NOW) for spec in case["activities"]]
    insights = [_insight(spec, _FIXED_NOW) for spec in case.get("insights", [])]
    agent, _ = _make_agent(case["mock"])
    outcome = await agent.generate_recommendations(
        profile=profile,
        activities=activities,
        insights=insights,
        user_id="user-1",
        now=_FIXED_NOW,
    )
    expect = case["expect"]
    assert outcome.status == expect["status"]

    if expect["status"] == "success":
        assert isinstance(outcome, CoachSuccess)
        assert len(outcome.recommendations) == expect["rec_count"]
        payload_recs = case["mock"]["payload"]["recommendations"]
        seen_ids: set[str] = set()
        for rec in outcome.recommendations:
            draft = next(item for item in payload_recs if item.get("title") == rec.title)
            basis = _BASIS_ADAPTER.validate_python(draft["saving_basis"])
            expected, _note = _evaluate_basis(basis, emission_service=_SERVICE, state=state)
            assert expected is not None
            assert rec.expected_saving_kg == pytest.approx(expected)
            assert rec.expected_saving_kg > 0
            assert rec.accepted is False
            assert rec.user_id == "user-1"
            assert rec.generated_at == _FIXED_NOW
            assert len(rec.id) == 32
            assert rec.id not in seen_ids
            seen_ids.add(rec.id)
            reasoning = rec.agent_reasoning
            assert reasoning is not None
            assert reasoning.agent_name == "coach"
            assert reasoning.prompt_version == "coach-v1"
            assert reasoning.model == "models/gemini-2.5-flash"
            assert reasoning.reasoning_steps
            assert reasoning.latency_ms >= 0
        if "reasoning_contains" in expect:
            joined = " ".join(
                step
                for rec in outcome.recommendations
                if rec.agent_reasoning is not None
                for step in rec.agent_reasoning.reasoning_steps
            )
            assert expect["reasoning_contains"] in joined
    elif expect["status"] == "empty":
        assert isinstance(outcome, CoachEmpty)
        assert outcome.reason
        assert outcome.agent_reasoning.agent_name == "coach"
    else:
        assert isinstance(outcome, CoachFailed)
        assert outcome.reason
        assert outcome.agent_reasoning.agent_name == "coach"


def test_evaluate_basis_transport_swap() -> None:
    basis = TransportSwapBasis(
        kind="transport_swap", from_mode="taxi_petrol", to_mode="metro", weekly_km=50
    )
    saving, note = _evaluate_basis(basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA)
    from_value = _SERVICE.get_transport_factor("taxi_petrol")
    to_value = _SERVICE.get_transport_factor("metro")
    assert from_value is not None
    assert to_value is not None
    expected = round((from_value.entry.value - to_value.entry.value) * 50, 4)
    assert saving == pytest.approx(expected)
    assert "transport_swap" in note


def test_evaluate_basis_electricity_reduce() -> None:
    basis = ElectricityReduceBasis(kind="electricity_reduce", weekly_kwh_reduction=10)
    saving, note = _evaluate_basis(basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA)
    grid = _SERVICE.get_grid_factor(IndianState.MAHARASHTRA)
    expected = round(grid.entry.value * 10, 4)
    assert saving == pytest.approx(expected)
    assert "electricity_reduce" in note


def test_evaluate_basis_food_swap() -> None:
    basis = FoodSwapBasis(
        kind="food_swap",
        from_category="non_veg_meal_chicken",
        to_category="veg_meal",
        weekly_meals=2,
    )
    saving, note = _evaluate_basis(basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA)
    from_food = _SERVICE.get_food_factor("non_veg_meal_chicken")
    to_food = _SERVICE.get_food_factor("veg_meal")
    assert from_food is not None
    assert to_food is not None
    expected = round((from_food.entry.value - to_food.entry.value) * 2, 4)
    assert saving == pytest.approx(expected)
    assert "food_swap" in note


def test_evaluate_basis_unknown_transport_mode_none() -> None:
    basis = TransportSwapBasis(
        kind="transport_swap", from_mode="taxi_petrol", to_mode="hyperloop", weekly_km=10
    )
    saving, note = _evaluate_basis(basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA)
    assert saving is None
    assert "unknown transport mode" in note


def test_evaluate_basis_unknown_food_category_none() -> None:
    basis = FoodSwapBasis(
        kind="food_swap", from_category="veg_meal", to_category="caviar", weekly_meals=1
    )
    saving, note = _evaluate_basis(basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA)
    assert saving is None
    assert "unknown food category" in note


def test_evaluate_basis_transport_no_saving_none() -> None:
    basis = TransportSwapBasis(
        kind="transport_swap", from_mode="metro", to_mode="taxi_petrol", weekly_km=10
    )
    saving, note = _evaluate_basis(basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA)
    assert saving is None
    assert "saves nothing" in note


def test_evaluate_basis_food_no_saving_none() -> None:
    basis = FoodSwapBasis(
        kind="food_swap",
        from_category="veg_meal",
        to_category="non_veg_meal_chicken",
        weekly_meals=3,
    )
    saving, note = _evaluate_basis(basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA)
    assert saving is None
    assert "saves nothing" in note


def test_evaluate_basis_below_threshold_none() -> None:
    basis = ElectricityReduceBasis(kind="electricity_reduce", weekly_kwh_reduction=0.005)
    saving, note = _evaluate_basis(basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA)
    assert saving is None
    assert "threshold" in note


def test_build_user_prompt_skips_unknown_factors() -> None:
    activities = [
        _activity(
            {
                "id": "a1",
                "type": "transport",
                "emission_kg_co2e": 1.0,
                "raw_input": "mystery ride",
                "structured_data": {"mode": "unknown_mode"},
            },
            _FIXED_NOW,
        ),
        _activity(
            {
                "id": "a2",
                "type": "food",
                "emission_kg_co2e": 1.0,
                "raw_input": "mystery meal",
                "structured_data": {"category": "unknown_category"},
            },
            _FIXED_NOW,
        ),
    ]
    buckets = {"this_week": activities, "last_week": [], "earlier": []}
    text = build_user_prompt(
        IndianState("Maharashtra"),
        HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="non-veg"),
        buckets,
        [],
    )
    assert "EMISSION FACTORS" in text
    assert "unknown_mode" not in text
    assert "unknown_category" not in text


async def test_coach_not_onboarded_returns_empty() -> None:
    profile = _profile("Maharashtra").model_copy(update={"state": None, "home_profile": None})
    agent, model = _make_agent({"kind": "raw", "text": "{}"})
    outcome = await agent.generate_recommendations(
        profile=profile,
        activities=[],
        insights=[],
        user_id="user-1",
        now=_FIXED_NOW,
    )
    assert isinstance(outcome, CoachEmpty)
    assert "onboarding" in outcome.reason.lower()
    model.generate_content_async.assert_not_called()


def test_coach_constructor_user_state_stored() -> None:
    model = MagicMock()
    model.model_name = "models/gemini-2.5-flash"
    factory = MagicMock()
    factory.flash.return_value = model
    agent = CoachAgent(
        emission_service=_SERVICE,
        gemini_factory=factory,
        user_state=IndianState.KERALA,
    )
    assert agent._user_state == IndianState.KERALA


@pytest.mark.parametrize("text", ["totally not json", '{"x": 1}', '{"recommendations": 7}'])
async def test_coach_malformed_shapes_fail(text: str) -> None:
    profile = _profile("Maharashtra")
    activities = [
        _activity(
            {
                "id": "a1",
                "type": "transport",
                "emission_kg_co2e": 2.04,
                "raw_input": "Uber to office",
                "structured_data": {"mode": "taxi_petrol", "km": 12.0},
            },
            _FIXED_NOW,
        )
    ]
    agent, _ = _make_agent({"kind": "raw", "text": text})
    outcome = await agent.generate_recommendations(
        profile=profile, activities=activities, insights=[], user_id="u", now=_FIXED_NOW
    )
    assert isinstance(outcome, CoachFailed)


async def test_coach_generic_model_error_fails() -> None:
    profile = _profile("Maharashtra")
    activities = [
        _activity(
            {
                "id": "a1",
                "type": "food",
                "emission_kg_co2e": 2.1,
                "raw_input": "chicken lunch",
                "structured_data": {"category": "non_veg_meal_chicken", "servings": 1.0},
            },
            _FIXED_NOW,
        )
    ]
    agent, _ = _make_agent({"kind": "raise", "exception": "RuntimeError"})
    outcome = await agent.generate_recommendations(
        profile=profile, activities=activities, insights=[], user_id="u", now=_FIXED_NOW
    )
    assert isinstance(outcome, CoachFailed)
    assert "failed" in outcome.reason.lower()


async def test_coach_recommendations_capped_at_three() -> None:
    profile = _profile("Maharashtra")
    activities = [
        _activity(
            {
                "id": "a1",
                "type": "transport",
                "emission_kg_co2e": 2.04,
                "raw_input": "Uber to office",
                "structured_data": {"mode": "taxi_petrol", "km": 12.0},
            },
            _FIXED_NOW,
        )
    ]
    payload = {
        "recommendations": [
            {
                "type": "swap",
                "title": f"Rec {i}",
                "description": "Take the metro instead of a cab.",
                "difficulty": "easy",
                "saving_basis": {
                    "kind": "transport_swap",
                    "from_mode": "taxi_petrol",
                    "to_mode": "metro",
                    "weekly_km": 20,
                },
            }
            for i in range(4)
        ]
    }
    agent, _ = _make_agent({"kind": "json", "payload": payload})
    outcome = await agent.generate_recommendations(
        profile=profile, activities=activities, insights=[], user_id="u", now=_FIXED_NOW
    )
    assert isinstance(outcome, CoachSuccess)
    assert len(outcome.recommendations) == 3
