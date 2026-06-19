"""Recommendation domain model for CarbonSaathi.

A :class:`Recommendation` is an actionable, personalised suggestion produced
by the Coach agent and stored at ``users/{uid}/recommendations/{id}`` in
Firestore.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.shared import AgentReasoning, IsoTimestamp

RecType = Literal["swap", "reduce", "challenge"]
"""Classification of the recommendation.

``swap``      — replace one behaviour with a lower-emission alternative.
``reduce``    — do the same thing less (e.g. fewer AC hours).
``challenge`` — time-boxed goal with a measurable target.
"""

Difficulty = Literal["easy", "medium", "hard"]
"""Estimated effort required to adopt the recommendation."""


class Recommendation(BaseModel):
    """An AI-generated personalised action for reducing carbon footprint.

    Attributes:
        id: Client-assigned UUID (used as the Firestore document ID).
        user_id: Firebase UID of the owning user.
        generated_at: When the recommendation was produced (UTC, timezone-aware).
        type: Semantic category of the suggestion.
        title: Short heading displayed in the UI (1-200 chars).
        description: Full explanation shown on expand (1-2000 chars).
        expected_saving_kg: Estimated emission reduction in kg CO₂e (≥ 0,
            4-decimal precision recommended).
        difficulty: Estimated adoption effort.
        accepted: ``True`` once the user taps "Accept" in the UI.
        agent_reasoning: Reasoning trace from the Coach agent; ``None`` if
            created programmatically.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    user_id: str
    generated_at: IsoTimestamp
    type: RecType
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    expected_saving_kg: float = Field(ge=0, description="kg CO2e, 4-decimal precision recommended")
    difficulty: Difficulty
    accepted: bool = False
    agent_reasoning: AgentReasoning | None = None
