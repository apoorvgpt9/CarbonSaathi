"""End-to-end integration test for the Logger -> Analyst -> Coach agent chain.

Instantiates all three agents with mocked Gemini factories and runs a single
realistic scenario through the full pipeline.  No network access occurs.  This
is the smoke check that the sequential-agent architecture composes as designed:
each stage returns a success outcome, every output carries a populated reasoning
trace with the correct agent name, and the Coach's savings are deterministic.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import google.generativeai as genai
import pytest
from pydantic import TypeAdapter

from app.agents.analyst_agent import AnalystAgent, AnalystSuccess
from app.agents.coach_agent import CoachAgent, CoachSuccess, SavingBasis, _evaluate_basis
from app.agents.logger_agent import LoggerAgent, LoggerSuccess
from app.models.activity import Activity
from app.models.user import HomeProfile, IndianState, UserProfile
from app.services.emission_service import get_emission_service

_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
_BASIS_ADAPTER: TypeAdapter[Any] = TypeAdapter(SavingBasis)


def _factory_for(model: MagicMock) -> MagicMock:
    factory = MagicMock()
    factory.flash.return_value = model
    factory.pro.return_value = model
    return factory


def _flash_function_call_model(name: str, args: dict[str, Any]) -> MagicMock:
    function_call = genai.protos.FunctionCall(name=name, args=args)
    part = SimpleNamespace(function_call=function_call)
    content = SimpleNamespace(parts=[part])
    response = SimpleNamespace(candidates=[SimpleNamespace(content=content)])
    model = MagicMock()
    model.model_name = "models/gemini-2.5-flash"
    model.generate_content_async = AsyncMock(return_value=response)
    return model


def _pro_json_model(payload: dict[str, Any]) -> MagicMock:
    model = MagicMock()
    model.model_name = "models/gemini-2.5-pro"
    model.generate_content_async = AsyncMock(return_value=SimpleNamespace(text=json.dumps(payload)))
    return model


def _build_activity(
    activity_id: str,
    activity_type: str,
    days_ago: int,
    raw_input: str,
    structured_data: dict[str, Any],
    emission_kg: float,
    source: str,
) -> Activity:
    return Activity(
        id=activity_id,
        user_id="user-1",
        type=activity_type,
        timestamp=_NOW - timedelta(days=days_ago),
        raw_input=raw_input,
        structured_data=structured_data,
        emission_kg_co2e=emission_kg,
        confidence="medium",
        emission_factor_source=source,
        agent_reasoning=None,
    )


@pytest.mark.integration
async def test_logger_analyst_coach_chain() -> None:
    service = get_emission_service()

    # --- Step 1: Logger captures one activity from free text. ---
    logger_model = _flash_function_call_model("log_transport", {"mode": "taxi_petrol", "km": 12.0})
    logger = LoggerAgent(emission_service=service, gemini_factory=_factory_for(logger_model))
    logged = await logger.log_activity(
        user_input="Took an Uber to office, about 12 km",
        user_state=IndianState.MAHARASHTRA,
        activity_id="act-logger",
        user_id="user-1",
        now=_NOW,
    )
    assert isinstance(logged, LoggerSuccess)
    first_activity = logged.activity
    assert first_activity.agent_reasoning is not None
    assert first_activity.agent_reasoning.agent_name == "logger"

    # --- Step 2: Analyst studies four activities (1 logged + 3 hand-built). ---
    activities = [
        first_activity,
        _build_activity(
            "act-2", "electricity", 2, "AC ran about 8 units", {"kwh": 8.0}, 6.3, "CEA 2023"
        ),
        _build_activity(
            "act-3",
            "food",
            3,
            "chicken biryani lunch",
            {"category": "non_veg_meal_chicken", "servings": 1.0},
            2.1,
            "FAO 2022",
        ),
        _build_activity(
            "act-4",
            "transport",
            9,
            "auto to the market",
            {"mode": "auto_rickshaw_cng", "km": 5.0},
            0.33,
            "ICCT 2023",
        ),
    ]
    analyst_payload = {
        "insights": [
            {
                "type": "pattern",
                "title": "Cab commuting",
                "description": "You rely on cabs for the office commute.",
                "supporting_activity_ids": ["act-logger"],
            },
            {
                "type": "trend",
                "title": "Transport and food lead",
                "description": "Transport and food drive most of your footprint.",
                "supporting_activity_ids": ["act-3", "act-4"],
            },
            {
                "type": "milestone",
                "title": "Four activities logged",
                "description": "You have now logged four activities.",
                "supporting_activity_ids": [],
            },
        ]
    }
    analyst = AnalystAgent(gemini_factory=_factory_for(_pro_json_model(analyst_payload)))
    analysed = await analyst.generate_insights(activities=activities, user_id="user-1", now=_NOW)
    assert isinstance(analysed, AnalystSuccess)
    assert len(analysed.insights) == 3
    valid_ids = {activity.id for activity in activities}
    for insight in analysed.insights:
        assert insight.agent_reasoning is not None
        assert insight.agent_reasoning.agent_name == "analyst"
        assert set(insight.supporting_activity_ids) <= valid_ids

    # --- Step 3: Coach turns activities + insights + profile into recommendations. ---
    profile = UserProfile(
        uid="user-1",
        email="user@example.com",
        display_name="User",
        state=IndianState.MAHARASHTRA,
        home_profile=HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="non-veg"),
        created_at=_NOW,
        last_active=_NOW,
        onboarding_complete=True,
    )
    coach_payload = {
        "recommendations": [
            {
                "type": "swap",
                "title": "Metro over cab",
                "description": "Take the metro for your office commute.",
                "difficulty": "easy",
                "saving_basis": {
                    "kind": "transport_swap",
                    "from_mode": "taxi_petrol",
                    "to_mode": "metro",
                    "weekly_km": 60,
                },
            },
            {
                "type": "reduce",
                "title": "Trim AC use",
                "description": "Run the AC one hour less each night.",
                "difficulty": "medium",
                "saving_basis": {"kind": "electricity_reduce", "weekly_kwh_reduction": 7},
            },
            {
                "type": "swap",
                "title": "Veg thali Thursdays",
                "description": "Swap a weekly chicken lunch for a veg thali.",
                "difficulty": "easy",
                "saving_basis": {
                    "kind": "food_swap",
                    "from_category": "non_veg_meal_chicken",
                    "to_category": "veg_meal",
                    "weekly_meals": 2,
                },
            },
        ]
    }
    coach = CoachAgent(
        emission_service=service, gemini_factory=_factory_for(_pro_json_model(coach_payload))
    )
    coached = await coach.generate_recommendations(
        profile=profile,
        activities=activities,
        insights=analysed.insights,
        user_id="user-1",
        now=_NOW,
    )
    assert isinstance(coached, CoachSuccess)
    assert len(coached.recommendations) == 3
    payload_recs = coach_payload["recommendations"]
    for rec in coached.recommendations:
        assert rec.agent_reasoning is not None
        assert rec.agent_reasoning.agent_name == "coach"
        assert rec.accepted is False
        assert rec.expected_saving_kg > 0
        draft = next(item for item in payload_recs if item["title"] == rec.title)
        basis = _BASIS_ADAPTER.validate_python(draft["saving_basis"])
        expected, _note = _evaluate_basis(
            basis, emission_service=service, state=IndianState.MAHARASHTRA
        )
        assert expected is not None
        assert rec.expected_saving_kg == pytest.approx(expected)

    # --- Chain-wide invariants: every reasoning trace is populated. ---
    reasonings = [
        first_activity.agent_reasoning,
        *[insight.agent_reasoning for insight in analysed.insights],
        *[rec.agent_reasoning for rec in coached.recommendations],
    ]
    assert len(reasonings) == 7
    for reasoning in reasonings:
        assert reasoning is not None
        assert reasoning.latency_ms >= 0
        assert reasoning.reasoning_steps
