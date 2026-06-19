"""Tests for app/agents/logger_agent.py — LoggerAgent and LoggerOutcome.

All Gemini calls are mocked; no network access occurs.  The golden suite drives
the happy paths and the main failure/rejection branches from JSON fixtures, with
targeted unit tests covering helpers and validation edges.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import google.generativeai as genai
import pytest

from app.agents.logger_agent import (
    AVG_INR_PER_KWH,
    LoggerAgent,
    LoggerFailed,
    LoggerRejected,
    LoggerSuccess,
    _extract_function_call,
    _summarise,
)
from app.agents.prompts.logger_v1 import FUNCTION_DECLARATIONS
from app.models.user import IndianState
from app.services.emission_service import get_emission_service

_GOLDEN_DIR = Path(__file__).parent / "fixtures" / "agent_goldens" / "logger"
_GOLDENS = sorted(_GOLDEN_DIR.glob("*.json"))
_FIXED_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _build_response(mock: dict[str, Any]) -> SimpleNamespace:
    if mock["kind"] == "function_call":
        function_call = genai.protos.FunctionCall(
            name=mock["function_name"],
            args=mock["function_args"],
        )
        part = SimpleNamespace(function_call=function_call)
    else:
        part = SimpleNamespace(function_call=None)
    content = SimpleNamespace(parts=[part])
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


def _make_agent(mock: dict[str, Any]) -> LoggerAgent:
    model = MagicMock()
    model.model_name = "models/gemini-2.5-flash"
    kind = mock.get("kind")
    if kind == "raise":
        exc_type = {"TimeoutError": TimeoutError, "RuntimeError": RuntimeError}[mock["exception"]]
        model.generate_content_async = AsyncMock(side_effect=exc_type())
    elif kind in (None, "none"):
        model.generate_content_async = AsyncMock(
            side_effect=AssertionError("model must not be called"),
        )
    else:
        model.generate_content_async = AsyncMock(return_value=_build_response(mock))
    factory = MagicMock()
    factory.flash.return_value = model
    return LoggerAgent(emission_service=get_emission_service(), gemini_factory=factory)


def _find_declaration(name: str) -> Any:
    for declaration in FUNCTION_DECLARATIONS:
        if declaration.name == name:
            return declaration
    raise AssertionError(f"declaration '{name}' not found")


@pytest.mark.parametrize("path", _GOLDENS, ids=lambda p: p.stem)
async def test_logger_golden(path: Path) -> None:
    case = _load(path)
    agent = _make_agent(case["mock"])
    outcome = await agent.log_activity(
        user_input=case["user_input"],
        user_state=IndianState(case["user_state"]),
        activity_id="act-1",
        user_id="user-1",
        now=_FIXED_NOW,
    )
    expect = case["expect"]
    assert outcome.status == expect["status"]

    if expect["status"] == "success":
        assert isinstance(outcome, LoggerSuccess)
        activity = outcome.activity
        assert activity.type == expect["type"]
        assert activity.emission_kg_co2e == pytest.approx(expect["emission_kg_co2e"])
        assert activity.confidence == expect["confidence"]
        assert expect["source_contains"] in activity.emission_factor_source
        for key, value in expect["structured_subset"].items():
            assert activity.structured_data[key] == value
        assert activity.timestamp == _FIXED_NOW
        assert activity.agent_reasoning is not None
        assert activity.agent_reasoning.agent_name == "logger"
        assert activity.agent_reasoning.prompt_version == "logger-v1"
        assert activity.agent_reasoning.model == "models/gemini-2.5-flash"
        assert activity.agent_reasoning.reasoning_steps
        assert activity.agent_reasoning.latency_ms >= 0
    elif expect["status"] == "rejected":
        assert isinstance(outcome, LoggerRejected)
        assert outcome.category == expect["category"]
        assert outcome.reason
        assert outcome.agent_reasoning.agent_name == "logger"
    else:
        assert isinstance(outcome, LoggerFailed)
        assert expect["reason_contains"] in outcome.reason
        assert outcome.agent_reasoning.agent_name == "logger"


def test_transport_enum_matches_factor_data() -> None:
    declaration = _find_declaration("log_transport")
    enum_values = list(declaration.parameters.properties["mode"].enum)
    assert enum_values == get_emission_service().list_transport_modes()


def test_food_enum_matches_factor_data() -> None:
    declaration = _find_declaration("log_food")
    enum_values = list(declaration.parameters.properties["category"].enum)
    assert enum_values == get_emission_service().list_food_categories()


async def test_bill_conversion_sets_note_and_estimated() -> None:
    agent = _make_agent(
        {
            "kind": "function_call",
            "function_name": "log_electricity",
            "function_args": {"bill_amount_inr": 800.0},
        }
    )
    outcome = await agent.log_activity(
        user_input="electricity bill was 800 rupees",
        user_state=IndianState.MAHARASHTRA,
        activity_id="a",
        user_id="u",
        now=_FIXED_NOW,
    )
    assert isinstance(outcome, LoggerSuccess)
    structured = outcome.activity.structured_data
    assert structured["kwh"] == pytest.approx(100.0)
    assert structured["bill_amount_inr"] == pytest.approx(800.0)
    assert f"{AVG_INR_PER_KWH} INR/kWh" in structured["notes"]
    assert "800" in structured["notes"]
    assert outcome.activity.confidence == "estimated"


async def test_unknown_function_name_fails() -> None:
    agent = _make_agent(
        {"kind": "function_call", "function_name": "log_unknown", "function_args": {}}
    )
    outcome = await agent.log_activity(
        user_input="logged my metro commute",
        user_state=IndianState.MAHARASHTRA,
        activity_id="a",
        user_id="u",
        now=_FIXED_NOW,
    )
    assert isinstance(outcome, LoggerFailed)
    assert "unknown function" in outcome.reason.lower()


async def test_generic_sdk_error_fails() -> None:
    agent = _make_agent({"kind": "raise", "exception": "RuntimeError"})
    outcome = await agent.log_activity(
        user_input="took the metro to office",
        user_state=IndianState.MAHARASHTRA,
        activity_id="a",
        user_id="u",
        now=_FIXED_NOW,
    )
    assert isinstance(outcome, LoggerFailed)
    assert "failed" in outcome.reason.lower()


async def test_invalid_food_servings_fails() -> None:
    agent = _make_agent(
        {
            "kind": "function_call",
            "function_name": "log_food",
            "function_args": {"category": "veg_meal", "servings": 0},
        }
    )
    outcome = await agent.log_activity(
        user_input="ate a veg meal",
        user_state=IndianState.MAHARASHTRA,
        activity_id="a",
        user_id="u",
        now=_FIXED_NOW,
    )
    assert isinstance(outcome, LoggerFailed)
    assert "invalid food" in outcome.reason.lower()


async def test_invalid_transport_km_fails() -> None:
    agent = _make_agent(
        {
            "kind": "function_call",
            "function_name": "log_transport",
            "function_args": {"mode": "metro", "km": 20000.0},
        }
    )
    outcome = await agent.log_activity(
        user_input="took metro a very long way",
        user_state=IndianState.MAHARASHTRA,
        activity_id="a",
        user_id="u",
        now=_FIXED_NOW,
    )
    assert isinstance(outcome, LoggerFailed)
    assert "invalid transport" in outcome.reason.lower()


async def test_invalid_electricity_empty_fails() -> None:
    agent = _make_agent(
        {
            "kind": "function_call",
            "function_name": "log_electricity",
            "function_args": {"appliance": "AC"},
        }
    )
    outcome = await agent.log_activity(
        user_input="ran the AC on electricity",
        user_state=IndianState.MAHARASHTRA,
        activity_id="a",
        user_id="u",
        now=_FIXED_NOW,
    )
    assert isinstance(outcome, LoggerFailed)
    assert "invalid electricity" in outcome.reason.lower()


async def test_unknown_food_category_fails() -> None:
    agent = _make_agent(
        {
            "kind": "function_call",
            "function_name": "log_food",
            "function_args": {"category": "caviar", "servings": 1.0},
        }
    )
    outcome = await agent.log_activity(
        user_input="ate some fancy food",
        user_state=IndianState.MAHARASHTRA,
        activity_id="a",
        user_id="u",
        now=_FIXED_NOW,
    )
    assert isinstance(outcome, LoggerFailed)
    assert "unknown food category" in outcome.reason.lower()


def test_summarise_truncates_long_input() -> None:
    summary = _summarise("metro " * 60)
    assert len(summary) <= 120
    assert summary.endswith("…")


def test_summarise_collapses_whitespace() -> None:
    assert _summarise("took   the\n metro") == "took the metro"


def test_extract_function_call_handles_empty_response() -> None:
    assert _extract_function_call(SimpleNamespace(candidates=[])) is None

    no_content = SimpleNamespace(candidates=[SimpleNamespace(content=None)])
    assert _extract_function_call(no_content) is None

    no_parts = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))])
    assert _extract_function_call(no_parts) is None
