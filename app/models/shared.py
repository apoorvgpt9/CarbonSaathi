"""Shared Pydantic types and helpers used across all CarbonSaathi domain models.

Provides :class:`AgentReasoning` (the visible-reasoning envelope attached to every
AI-generated entity) and the :data:`IsoTimestamp` annotated type alias that enforces
timezone-aware UTC datetimes throughout the data model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _enforce_utc(value: datetime) -> datetime:
    """Coerce a datetime to UTC, rejecting naive values.

    Args:
        value: The incoming datetime value from Pydantic validation.

    Returns:
        The datetime converted to UTC.

    Raises:
        ValueError: If ``value`` has no timezone information (naive datetime).
    """
    if value.tzinfo is None:
        raise ValueError(
            "datetime must be timezone-aware; pass a UTC datetime or one with explicit tzinfo"
        )
    return value.astimezone(UTC)


IsoTimestamp = Annotated[datetime, AfterValidator(_enforce_utc)]
"""UTC-enforced datetime alias.

Any timezone-aware datetime is accepted and silently converted to UTC.
Naive datetimes are rejected with a ``ValueError``.
"""


class AgentReasoning(BaseModel):
    """Trace envelope captured by an AI agent during a single inference pass.

    Attached to :class:`~app.models.activity.Activity`,
    :class:`~app.models.insight.Insight`, and
    :class:`~app.models.recommendation.Recommendation` to power the
    "show your work" UI differentiator.

    Attributes:
        agent_name: Which of the three sequential agents produced this trace.
        prompt_version: Semver-style string identifying the prompt template used
            (e.g. ``"1.0.0"``). Used to correlate regressions across deploys.
        input_summary: A human-readable one-liner of what the agent received.
        reasoning_steps: Ordered list of intermediate reasoning steps emitted
            by the agent (may be streamed to the UI via SSE).
        output_summary: A human-readable one-liner of what the agent produced.
        model: The Gemini model identifier (e.g. ``"gemini-2.5-flash"``).
        latency_ms: Wall-clock inference latency in milliseconds (``>= 0``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_name: Literal["logger", "analyst", "coach"]
    prompt_version: str
    input_summary: str
    reasoning_steps: list[str]
    output_summary: str
    model: str
    latency_ms: int = Field(ge=0)
