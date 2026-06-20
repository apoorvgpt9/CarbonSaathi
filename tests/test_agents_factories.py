"""Tests for app/agents/factories.py — get_logger_agent singleton."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agents.factories import get_logger_agent
from app.agents.logger_agent import LoggerAgent


def test_get_logger_agent_returns_logger_agent_and_caches() -> None:
    """get_logger_agent() returns a LoggerAgent and caches the same instance."""
    get_logger_agent.cache_clear()
    try:
        model_mock = MagicMock()
        model_mock.model_name = "models/gemini-2.5-flash"

        factory_mock = MagicMock()
        factory_mock.flash.return_value = model_mock

        with (
            patch("app.agents.factories.get_emission_service") as mock_es,
            patch("app.agents.factories.get_gemini_client") as mock_gc,
        ):
            mock_es.return_value = MagicMock()
            mock_gc.return_value = factory_mock

            agent1 = get_logger_agent()
            agent2 = get_logger_agent()

        assert isinstance(agent1, LoggerAgent)
        assert agent1 is agent2  # lru_cache returns the same instance
    finally:
        get_logger_agent.cache_clear()
