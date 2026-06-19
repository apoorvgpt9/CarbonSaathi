"""Base agent infrastructure for CarbonSaathi's sequential AI agents.

Provides :class:`BaseAgent`, an abstract base owning the cross-cutting concerns
shared by the Logger, Analyst, and Coach agents: input governance, latency
measurement, :class:`~app.models.shared.AgentReasoning` assembly, and structured
logging.  Concrete agents define their own typed entrypoint; the base
intentionally does **not** prescribe a ``run`` signature.
"""

from __future__ import annotations

import time
from abc import ABC
from typing import Any, Literal

import structlog

from app.core import governance
from app.core.governance import GovernanceResult
from app.models.shared import AgentReasoning

_logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class AgentInvocationError(Exception):
    """Raised when an agent encounters a genuinely unexpected error.

    Distinct from handled outcomes (governance rejection, model failure), which
    concrete agents return as typed values rather than raising.
    """


class BaseAgent(ABC):  # noqa: B024  # shared-helper base; subclasses define their own entrypoint
    """Abstract base for CarbonSaathi's sequential AI agents.

    Args:
        prompt_version: Version string of the prompt template the concrete agent
            uses (e.g. ``"logger-v1"``).
        model_name: The Gemini model identifier the agent calls.
    """

    def __init__(self, *, prompt_version: str, model_name: str) -> None:
        """Store the prompt version and model name for reasoning traces."""
        self._prompt_version = prompt_version
        self._model_name = model_name

    def _check_governance(self, text: str) -> GovernanceResult:
        """Run the input governance gate.

        Args:
            text: Raw user input to classify.

        Returns:
            The :class:`~app.core.governance.GovernanceResult`.
        """
        return governance.check_input(text)

    @staticmethod
    def _now_ms() -> int:
        """Return a monotonic timestamp in milliseconds.

        Returns:
            Milliseconds from an arbitrary monotonic origin; only the difference
            between two calls is meaningful (used for latency measurement).
        """
        return time.monotonic_ns() // 1_000_000

    def _build_reasoning(
        self,
        *,
        agent_name: Literal["logger", "analyst", "coach"],
        input_summary: str,
        steps: list[str],
        output_summary: str,
        latency_ms: int,
    ) -> AgentReasoning:
        """Assemble an :class:`AgentReasoning` trace from agent-supplied parts.

        Args:
            agent_name: Which agent produced the trace.
            input_summary: One-line description of the input.
            steps: Ordered intermediate reasoning steps.
            output_summary: One-line description of the output.
            latency_ms: Inference latency in milliseconds (\u2265 0).

        Returns:
            A populated :class:`AgentReasoning` instance.
        """
        return AgentReasoning(
            agent_name=agent_name,
            prompt_version=self._prompt_version,
            input_summary=input_summary,
            reasoning_steps=steps,
            output_summary=output_summary,
            model=self._model_name,
            latency_ms=latency_ms,
        )

    def _log(self, event: str, **kwargs: Any) -> None:
        """Emit a structured log event.

        Args:
            event: Event name / message.
            **kwargs: Structured key/value context.
        """
        _logger.info(event, **kwargs)
