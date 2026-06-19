"""Activity domain model for CarbonSaathi.

An :class:`Activity` represents a single carbon-emitting action logged by the
user (transport, electricity, or food).  It is written to
``users/{uid}/activities/{id}`` in Firestore by the Logger agent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.shared import AgentReasoning, IsoTimestamp

ActivityType = Literal["transport", "electricity", "food"]
"""Category of carbon-emitting activity."""

Confidence = Literal["high", "medium", "estimated"]
"""Confidence level of the emission calculation.

``high``      — activity fully matched a known emission factor.
``medium``    — factor inferred from partial data (e.g. trip distance estimated).
``estimated`` — significant assumptions were required.
"""


class Activity(BaseModel):
    """A single logged carbon-emitting event.

    Attributes:
        id: Client-assigned UUID (used as the Firestore document ID).
        user_id: Firebase UID of the owning user.
        type: Broad category of the activity.
        timestamp: When the activity occurred (UTC, timezone-aware).
        raw_input: Verbatim text submitted by the user (1-500 chars).
        structured_data: Agent-parsed key/value pairs (schema varies by type).
        emission_kg_co2e: Calculated emission in kg CO₂e (≥ 0, 4-decimal precision recommended).
        confidence: Reliability of the emission value.
        emission_factor_source: Citation string for the factor used (e.g. ``"CEA 2023"``)
        agent_reasoning: Full reasoning trace from the Logger agent; ``None`` if
            the activity was created programmatically without an agent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    user_id: str
    type: ActivityType
    timestamp: IsoTimestamp
    raw_input: str = Field(min_length=1, max_length=500)
    structured_data: dict[str, Any]
    emission_kg_co2e: float = Field(ge=0, description="kg CO2e, 4-decimal precision recommended")
    confidence: Confidence
    emission_factor_source: str = Field(min_length=1)
    agent_reasoning: AgentReasoning | None = None
