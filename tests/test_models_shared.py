"""Tests for app/models/shared.py — AgentReasoning and IsoTimestamp."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.shared import AgentReasoning, _enforce_utc


def _valid_reasoning(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "agent_name": "logger",
        "prompt_version": "1.0.0",
        "input_summary": "User took an Uber.",
        "reasoning_steps": ["Step 1", "Step 2"],
        "output_summary": "0.42 kg CO2e",
        "model": "gemini-2.5-flash",
        "latency_ms": 320,
    }
    base.update(overrides)
    return base


def test_agent_reasoning_valid_round_trip() -> None:
    r = AgentReasoning(**_valid_reasoning())
    assert r.agent_name == "logger"
    assert r.latency_ms == 320
    assert r.reasoning_steps == ["Step 1", "Step 2"]


def test_agent_reasoning_invalid_agent_name() -> None:
    with pytest.raises(ValidationError):
        AgentReasoning(**_valid_reasoning(agent_name="oracle"))


def test_agent_reasoning_missing_prompt_version() -> None:
    data = _valid_reasoning()
    del data["prompt_version"]
    with pytest.raises(ValidationError):
        AgentReasoning(**data)


def test_agent_reasoning_missing_reasoning_steps() -> None:
    data = _valid_reasoning()
    del data["reasoning_steps"]
    with pytest.raises(ValidationError):
        AgentReasoning(**data)


def test_agent_reasoning_missing_model_field() -> None:
    data = _valid_reasoning()
    del data["model"]
    with pytest.raises(ValidationError):
        AgentReasoning(**data)


def test_agent_reasoning_negative_latency_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentReasoning(**_valid_reasoning(latency_ms=-1))


def test_agent_reasoning_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentReasoning(**_valid_reasoning(unexpected="x"))


def test_agent_reasoning_is_frozen() -> None:
    r = AgentReasoning(**_valid_reasoning())
    with pytest.raises((AttributeError, ValidationError)):
        r.latency_ms = 999  # type: ignore[misc]


def test_iso_timestamp_naive_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _enforce_utc(datetime(2025, 1, 1))


def test_iso_timestamp_utc_passes() -> None:
    dt = datetime(2025, 1, 1, tzinfo=UTC)
    result = _enforce_utc(dt)
    assert result.tzinfo is not None
    assert result.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_iso_timestamp_non_utc_converted() -> None:
    from datetime import timedelta

    ist = timezone(timedelta(hours=5, minutes=30))
    dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=ist)
    result = _enforce_utc(dt)
    assert result.tzinfo == UTC
    assert result.hour == 6  # 12:00 IST == 06:30 UTC → hour=6
