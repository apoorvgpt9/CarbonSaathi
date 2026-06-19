"""Insight domain model for CarbonSaathi.

An :class:`Insight` is an AI-generated observation about a user's emission
patterns, stored at ``users/{uid}/insights/{id}`` in Firestore and produced
by the Analyst agent.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.shared import AgentReasoning, IsoTimestamp

InsightType = Literal["pattern", "trend", "milestone"]
"""Classification of the insight.

``pattern``   — recurring behaviour observed across activities.
``trend``     — direction of change over time (improving / worsening).
``milestone`` — a noteworthy threshold crossed (e.g. first week under 5 kg CO₂e).
"""


class Insight(BaseModel):
    """An AI-generated observation about a user's carbon footprint.

    Attributes:
        id: Client-assigned UUID (used as the Firestore document ID).
        user_id: Firebase UID of the owning user.
        generated_at: When the insight was produced (UTC, timezone-aware).
        type: Semantic category of the insight.
        title: Short heading displayed in the UI (1-200 chars).
        description: Full explanation shown on expand (1-2000 chars).
        supporting_activity_ids: List of :class:`~app.models.activity.Activity`
            IDs that ground this insight.
        agent_reasoning: Reasoning trace from the Analyst agent; ``None`` if
            created programmatically.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    user_id: str
    generated_at: IsoTimestamp
    type: InsightType
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    supporting_activity_ids: list[str]
    agent_reasoning: AgentReasoning | None = None
