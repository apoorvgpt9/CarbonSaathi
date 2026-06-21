"""Analyst agent: surfaces carbon-footprint insights via Gemini 2.5 Pro.

The :class:`AnalystAgent` reviews a user's recent
:class:`~app.models.activity.Activity` records and returns a list of
:class:`~app.models.insight.Insight` objects, each with a visible reasoning
trace.  Activities are pre-bucketed by week locally; Gemini is asked only to
phrase qualitative observations as JSON, and every insight is grounded against
the real activity IDs supplied as input.

Results are returned as the typed :data:`AnalystOutcome` discriminated union so
the API layer can branch on ``status`` without ``try``/``except``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated, Final, Literal
from uuid import uuid4

import google.generativeai as genai
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.base import BaseAgent
from app.agents.prompts.analyst_v1 import (
    PROMPT_VERSION,
    RESPONSE_SCHEMA,
    SYSTEM_INSTRUCTION,
    build_user_prompt,
)
from app.core.gemini import GenerativeModelFactory
from app.models.activity import Activity
from app.models.insight import Insight, InsightType
from app.models.shared import AgentReasoning

_GEMINI_TIMEOUT_S: Final[float] = 30.0
"""Maximum seconds to await a single Gemini Pro generation before failing."""

MIN_ACTIVITIES_FOR_INSIGHTS: Final[int] = 3
"""Minimum activities required before the Analyst will call the model.

Below this threshold the agent returns :class:`AnalystEmpty` immediately, with
no Gemini call, because too little data yields no trustworthy pattern.
"""

_MAX_INSIGHTS: Final[int] = 3
"""Upper bound on insights returned from a single analysis pass."""

_DAYS_PER_WEEK: Final[int] = 7
"""Number of days in a bucketing week."""

_REQUIRES_SUPPORT: Final[frozenset[str]] = frozenset({"pattern", "trend"})
"""Insight types that must cite at least one supporting activity ID."""

_INPUT_SUMMARY_LIMIT: Final[int] = 120
"""Maximum length of the reasoning input summary."""


def bucket_by_week(
    activities: list[Activity],
    *,
    now: datetime,
) -> dict[str, list[Activity]]:
    """Group activities into this-week / last-week / earlier buckets.

    Args:
        activities: Activities to group.
        now: Reference time; bucket membership is measured back from here.

    Returns:
        A mapping with keys ``this_week`` (0-6 days old), ``last_week`` (7-13
        days old), and ``earlier`` (14+ days old).  An activity exactly seven
        days old falls in ``last_week``.  Each bucket is sorted newest-first.
    """
    buckets: dict[str, list[Activity]] = {
        "this_week": [],
        "last_week": [],
        "earlier": [],
    }
    for activity in activities:
        days = (now - activity.timestamp).days
        if days < _DAYS_PER_WEEK:
            buckets["this_week"].append(activity)
        elif days < 2 * _DAYS_PER_WEEK:
            buckets["last_week"].append(activity)
        else:
            buckets["earlier"].append(activity)
    for bucket in buckets.values():
        bucket.sort(key=lambda activity: (activity.timestamp, activity.id), reverse=True)
    return buckets


class _InsightDraft(BaseModel):
    """Validation shell for one model-proposed insight.

    Uses ``extra="ignore"`` because the value is untrusted model output: a stray
    field should not cause an otherwise-valid insight to be dropped.

    Attributes:
        type: The insight category.
        title: Short heading (1-200 chars).
        description: Explanation (1-2000 chars).
        supporting_activity_ids: Candidate grounding IDs (filtered downstream).
    """

    model_config = ConfigDict(extra="ignore")

    type: InsightType
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    supporting_activity_ids: list[str] = Field(default_factory=list)


class AnalystSuccess(BaseModel):
    """One or more insights produced from the user's activities.

    Attributes:
        status: Discriminator literal ``"success"``.
        insights: The generated, grounded insights (at least one).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["success"] = "success"
    insights: list[Insight]


class AnalystEmpty(BaseModel):
    """The Analyst ran cleanly but had nothing meaningful to report.

    Returned for insufficient input data or when no draft survived validation.

    Attributes:
        status: Discriminator literal ``"empty"``.
        reason: Human-readable explanation.
        agent_reasoning: Reasoning trace describing the outcome.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["empty"] = "empty"
    reason: str
    agent_reasoning: AgentReasoning


class AnalystFailed(BaseModel):
    """The model call failed or returned unusable output.

    Attributes:
        status: Discriminator literal ``"failed"``.
        reason: Human-readable failure explanation.
        agent_reasoning: Reasoning trace describing the failure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["failed"] = "failed"
    reason: str
    agent_reasoning: AgentReasoning


AnalystOutcome = Annotated[
    AnalystSuccess | AnalystEmpty | AnalystFailed,
    Field(discriminator="status"),
]
"""Discriminated union of every possible Analyst result, keyed on ``status``."""


class AnalystAgent(BaseAgent):
    """Surfaces insights from a user's recent activities.

    Gemini Pro phrases the qualitative observations as JSON; all emission
    figures originate from the activities supplied by the caller.

    Args:
        gemini_factory: Builds the configured Gemini Pro model.
    """

    def __init__(self, *, gemini_factory: GenerativeModelFactory) -> None:
        """Build and cache the configured Pro model and JSON generation config."""
        model = gemini_factory.pro(system_instruction=SYSTEM_INSTRUCTION)
        super().__init__(prompt_version=PROMPT_VERSION, model_name=str(model.model_name))
        self._model = model
        self._generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        )

    async def generate_insights(
        self,
        *,
        activities: list[Activity],
        user_id: str,
        now: datetime | None = None,
    ) -> AnalystOutcome:
        """Produce grounded insights from a user's recent activities.

        Args:
            activities: The user's recent activities to analyse.
            user_id: Firebase UID of the owning user.
            now: Override for the insight timestamp and bucketing reference
                (defaults to the current UTC time).

        Returns:
            An :data:`AnalystOutcome`: :class:`AnalystSuccess` with at least one
            insight, :class:`AnalystEmpty` when there is nothing to report, or
            :class:`AnalystFailed` on a model error or malformed output.
        """
        start = self._now_ms()
        moment = now if now is not None else datetime.now(tz=UTC)
        steps: list[str] = []

        if len(activities) < MIN_ACTIVITIES_FOR_INSIGHTS:
            steps.append(f"Only {len(activities)} activities; need {MIN_ACTIVITIES_FOR_INSIGHTS}.")
            return AnalystEmpty(
                reason=(
                    f"Log at least {MIN_ACTIVITIES_FOR_INSIGHTS} activities to see "
                    "your patterns."
                ),
                agent_reasoning=self._reasoning(
                    input_summary=f"{len(activities)} activities",
                    steps=steps,
                    output_summary="No insights (insufficient data).",
                    start=start,
                ),
            )

        buckets = bucket_by_week(activities, now=moment)
        steps.append(
            f"Bucketed {len(activities)} activities "
            f"(this_week={len(buckets['this_week'])}, "
            f"last_week={len(buckets['last_week'])}, "
            f"earlier={len(buckets['earlier'])})."
        )
        prompt = build_user_prompt(buckets)
        input_summary = f"{len(activities)} activities across weekly buckets."

        try:
            response = await asyncio.wait_for(
                self._model.generate_content_async(
                    prompt, generation_config=self._generation_config
                ),
                timeout=_GEMINI_TIMEOUT_S,
            )
        except TimeoutError:
            return self._failed(
                "Gemini call timed out.",
                input_summary,
                [*steps, "Model call timed out."],
                start,
            )
        except Exception as exc:
            return self._failed(
                f"Gemini call failed: {exc}",
                input_summary,
                [*steps, "Model call raised an error."],
                start,
            )

        try:
            payload = json.loads(response.text)
            raw_insights = payload["insights"]
            if not isinstance(raw_insights, list):
                raise TypeError("'insights' must be a list")
        except (ValueError, KeyError, TypeError):
            return self._failed(
                "Model returned malformed JSON.",
                input_summary,
                [*steps, "Could not parse model JSON."],
                start,
            )
        steps.append(f"Model returned {len(raw_insights)} insight draft(s).")

        valid_ids = {activity.id for activity in activities}
        kept: list[tuple[_InsightDraft, list[str]]] = []
        for draft_data in raw_insights:
            if len(kept) >= _MAX_INSIGHTS:
                break
            try:
                draft = _InsightDraft.model_validate(draft_data)
            except ValidationError:
                steps.append("Dropped insight: invalid fields.")
                continue
            grounded = [aid for aid in draft.supporting_activity_ids if aid in valid_ids]
            if len(grounded) != len(draft.supporting_activity_ids):
                steps.append("Dropped activity IDs not present in the input.")
            if draft.type in _REQUIRES_SUPPORT and not grounded:
                steps.append(f"Dropped {draft.type} insight: no supporting activities.")
                continue
            kept.append((draft, grounded))

        if not kept:
            return AnalystEmpty(
                reason="No clear patterns found in your recent activity.",
                agent_reasoning=self._reasoning(
                    input_summary=input_summary,
                    steps=[*steps, "No insight survived validation."],
                    output_summary="No insights produced.",
                    start=start,
                ),
            )

        insights = [
            Insight(
                id=uuid4().hex,
                user_id=user_id,
                generated_at=moment,
                type=draft.type,
                title=draft.title,
                description=draft.description,
                supporting_activity_ids=grounded,
                agent_reasoning=self._reasoning(
                    input_summary=input_summary,
                    steps=[
                        *steps,
                        f"Kept {draft.type} insight grounded in {len(grounded)} activities.",
                    ],
                    output_summary=f"{draft.type}: {draft.title}",
                    start=start,
                ),
            )
            for draft, grounded in kept
        ]
        self._log("analyst.success", insight_count=len(insights))
        return AnalystSuccess(insights=insights)

    def _reasoning(
        self,
        *,
        input_summary: str,
        steps: list[str],
        output_summary: str,
        start: int,
    ) -> AgentReasoning:
        """Build an Analyst reasoning trace.

        Args:
            input_summary: One-line description of the input.
            steps: Ordered reasoning steps.
            output_summary: One-line description of the output.
            start: The ``_now_ms`` value captured at the start of the run.

        Returns:
            A populated :class:`AgentReasoning`.
        """
        return self._build_reasoning(
            agent_name="analyst",
            input_summary=input_summary[:_INPUT_SUMMARY_LIMIT],
            steps=steps,
            output_summary=output_summary,
            latency_ms=self._now_ms() - start,
        )

    def _failed(
        self,
        reason: str,
        input_summary: str,
        steps: list[str],
        start: int,
    ) -> AnalystFailed:
        """Assemble an :class:`AnalystFailed` outcome with a reasoning trace.

        Args:
            reason: Human-readable failure explanation.
            input_summary: One-line description of the input.
            steps: Reasoning steps accumulated up to the failure.
            start: The ``_now_ms`` value captured at the start of the run.

        Returns:
            A populated :class:`AnalystFailed`.
        """
        self._log("analyst.failed", reason=reason)
        return AnalystFailed(
            reason=reason,
            agent_reasoning=self._reasoning(
                input_summary=input_summary,
                steps=steps,
                output_summary=f"Failed: {reason}",
                start=start,
            ),
        )
