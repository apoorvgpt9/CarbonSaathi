"""Tests for app/agents/base.py — BaseAgent shared infrastructure."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.base import AgentInvocationError, BaseAgent
from app.core.governance import GovernanceResult


class _ConcreteAgent(BaseAgent):
    """Minimal concrete agent for exercising the base class."""


def _make_agent() -> _ConcreteAgent:
    return _ConcreteAgent(prompt_version="test-v1", model_name="models/test-model")


def test_now_ms_returns_non_negative_int() -> None:
    agent = _make_agent()
    value = agent._now_ms()
    assert isinstance(value, int)
    assert value >= 0


def test_check_governance_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent()
    sentinel = GovernanceResult(allowed=True, reason=None, category="ok")
    calls: list[str] = []

    def fake_check(text: str) -> GovernanceResult:
        calls.append(text)
        return sentinel

    monkeypatch.setattr("app.core.governance.check_input", fake_check)
    result = agent._check_governance("metro to work")

    assert result is sentinel
    assert calls == ["metro to work"]


def test_build_reasoning_populates_all_fields() -> None:
    agent = _make_agent()
    reasoning = agent._build_reasoning(
        agent_name="logger",
        input_summary="took metro",
        steps=["step one", "step two"],
        output_summary="0.3 kg",
        latency_ms=12,
    )
    assert reasoning.agent_name == "logger"
    assert reasoning.prompt_version == "test-v1"
    assert reasoning.model == "models/test-model"
    assert reasoning.input_summary == "took metro"
    assert reasoning.reasoning_steps == ["step one", "step two"]
    assert reasoning.output_summary == "0.3 kg"
    assert reasoning.latency_ms == 12


def test_log_emits_structured_event(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent()
    events: list[tuple[str, dict[str, object]]] = []

    def fake_info(event: str, **kwargs: object) -> None:
        events.append((event, kwargs))

    monkeypatch.setattr("app.agents.base._logger", SimpleNamespace(info=fake_info))
    agent._log("test.event", foo="bar")

    assert events == [("test.event", {"foo": "bar"})]


def test_agent_invocation_error_is_exception() -> None:
    assert issubclass(AgentInvocationError, Exception)
    with pytest.raises(AgentInvocationError):
        raise AgentInvocationError("boom")
