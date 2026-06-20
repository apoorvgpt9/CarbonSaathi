"""Agent factory functions for dependency injection.

This module exposes a single cached accessor for each agent so that route
modules import one function rather than the agent class directly.  Keeping
construction here decouples routes from the agent's dependency graph.
"""

from __future__ import annotations

from functools import lru_cache

from app.agents.analyst_agent import AnalystAgent
from app.agents.coach_agent import CoachAgent
from app.agents.logger_agent import LoggerAgent
from app.core.gemini import get_gemini_client
from app.services.emission_service import get_emission_service


@lru_cache(maxsize=1)
def get_logger_agent() -> LoggerAgent:
    """Return the singleton :class:`~app.agents.logger_agent.LoggerAgent`.

    Constructs the agent once per process using the cached emission-service
    and Gemini client singletons.  Subsequent calls return the same instance.

    Returns:
        The application-wide :class:`~app.agents.logger_agent.LoggerAgent`.
    """
    return LoggerAgent(
        emission_service=get_emission_service(),
        gemini_factory=get_gemini_client(),
    )


@lru_cache(maxsize=1)
def get_analyst_agent() -> AnalystAgent:
    """Return the singleton :class:`~app.agents.analyst_agent.AnalystAgent`.

    The Analyst needs only the Gemini client; emission figures originate from
    the activities supplied at call time, not from the emission service.

    Returns:
        The application-wide :class:`~app.agents.analyst_agent.AnalystAgent`.
    """
    return AnalystAgent(gemini_factory=get_gemini_client())


@lru_cache(maxsize=1)
def get_coach_agent() -> CoachAgent:
    """Return the singleton :class:`~app.agents.coach_agent.CoachAgent`.

    Constructs the agent once per process using the cached emission-service
    and Gemini client singletons.  Subsequent calls return the same instance.

    Returns:
        The application-wide :class:`~app.agents.coach_agent.CoachAgent`.
    """
    return CoachAgent(
        emission_service=get_emission_service(),
        gemini_factory=get_gemini_client(),
    )
