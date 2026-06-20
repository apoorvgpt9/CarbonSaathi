"""Insight-generation orchestrator for CarbonSaathi.

Defines :func:`run_insight_pipeline`, the single async generator that runs the
Analyst -> Coach sequence, persists their outputs, and yields a typed stream of
:data:`OrchestratorEvent` values describing its progress.  The orchestrator is
*pure* with respect to transport concerns: it knows nothing about SSE or JSON.
Route wrappers in :mod:`app.routes.insights` adapt the event stream into either
Server-Sent Events or a single JSON response.

Staleness and empty-result caching are delegated to
:func:`app.services.staleness.is_pipeline_stale`.  When the cached result is
still fresh the pipeline short-circuits without calling either agent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Final, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from app.agents.analyst_agent import AnalystAgent
from app.agents.coach_agent import CoachAgent
from app.models.generation_state import GenerationState
from app.models.insight import Insight
from app.models.recommendation import Recommendation
from app.models.user import UserProfile
from app.services.firestore_service import FirestoreService
from app.services.staleness import is_pipeline_stale

_logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_RECENT_LIMIT: Final[int] = 10
"""How many cached insights/recommendations to return on the fresh-cache path."""

_ACTIVITY_WINDOW_DAYS: Final[int] = 14
"""Trailing window (days) of activities fed to the Analyst and Coach."""

_ACTIVITY_FETCH_LIMIT: Final[int] = 200
"""Upper bound on activities fetched for a single pipeline run."""

_COACH_SKIPPED_REASON: Final[str] = "Insufficient insight data"
"""Reason surfaced when the Coach is skipped because the Analyst produced none."""

_ANALYST_FAILED_MESSAGE: Final[str] = "Analyst step could not complete"
"""Client-safe message for an Analyst failure; never includes exception text."""

_COACH_FAILED_MESSAGE: Final[str] = "Coach step could not complete"
"""Client-safe message for a Coach failure; never includes exception text."""

PhaseStatus = Literal["success", "empty", "failed", "skipped", "cached"]
"""Terminal status of a single pipeline phase, as surfaced to the client."""


class PhaseStart(BaseModel):
    """Signals that a pipeline phase has begun.

    Attributes:
        event: Discriminator literal ``"phase_start"``.
        phase: Which agent phase started.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: Literal["phase_start"] = "phase_start"
    phase: Literal["analyst", "coach"]


class ReasoningStep(BaseModel):
    """One visible reasoning step emitted during a phase.

    Attributes:
        event: Discriminator literal ``"reasoning"``.
        phase: Which agent phase produced the step.
        step: A single line from the agent's ``reasoning_steps`` trace.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: Literal["reasoning"] = "reasoning"
    phase: Literal["analyst", "coach"]
    step: str


class PhaseComplete(BaseModel):
    """Signals that a pipeline phase has finished.

    Attributes:
        event: Discriminator literal ``"phase_complete"``.
        phase: Which agent phase finished.
        status: Terminal status of the phase.
        reason: Optional human-readable explanation (empty/failed/skipped).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: Literal["phase_complete"] = "phase_complete"
    phase: Literal["analyst", "coach"]
    status: PhaseStatus
    reason: str | None = None


class Done(BaseModel):
    """Terminal event carrying the final, persisted pipeline result.

    Attributes:
        event: Discriminator literal ``"done"``.
        insights: The persisted (or cached) insights.
        recommendations: The persisted (or cached) recommendations.
        analyst_status: Terminal status of the Analyst phase.
        coach_status: Terminal status of the Coach phase.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: Literal["done"] = "done"
    insights: list[Insight]
    recommendations: list[Recommendation]
    analyst_status: PhaseStatus
    coach_status: PhaseStatus


OrchestratorEvent = Annotated[
    PhaseStart | ReasoningStep | PhaseComplete | Done,
    Field(discriminator="event"),
]
"""Discriminated union of every event the orchestrator yields, keyed on ``event``."""


async def run_insight_pipeline(
    *,
    uid: str,
    profile: UserProfile,
    analyst: AnalystAgent,
    coach: CoachAgent,
    firestore: FirestoreService,
    now: datetime | None = None,
) -> AsyncIterator[OrchestratorEvent]:
    """Run the Analyst -> Coach pipeline, yielding a typed progress stream.

    On a fresh cache the pipeline short-circuits: it fetches the last persisted
    insights/recommendations, yields two ``cached`` :class:`PhaseComplete`
    events (no :class:`PhaseStart`, no :class:`ReasoningStep`), and a final
    :class:`Done`, without calling either agent or writing
    :class:`~app.models.generation_state.GenerationState`.

    Otherwise it runs the Analyst, then (when the Analyst produced insights) the
    Coach.  Empty and failed agent outcomes are recorded only in
    ``GenerationState``; only successful insights/recommendations are persisted
    to their collections.  Agent failures surface a fixed, client-safe message;
    the underlying reason is logged at ``ERROR`` level.

    Args:
        uid: Firebase UID of the user.
        profile: The user's profile (guaranteed to exist by Phase 5A auth).
        analyst: The Analyst agent.
        coach: The Coach agent.
        firestore: Persistence layer for reads and writes.
        now: Reference time (UTC, timezone-aware); defaults to ``datetime.now``.

    Yields:
        :data:`OrchestratorEvent` values, always terminating in exactly one
        :class:`Done`.
    """
    now_utc = now if now is not None else datetime.now(tz=UTC)

    staleness = await is_pipeline_stale(uid=uid, firestore=firestore, now_utc=now_utc)
    if not staleness.stale:
        cached_insights = await firestore.get_recent_insights(uid, limit=_RECENT_LIMIT)
        cached_recommendations = await firestore.get_recent_recommendations(
            uid, limit=_RECENT_LIMIT
        )
        yield PhaseComplete(phase="analyst", status="cached")
        yield PhaseComplete(phase="coach", status="cached")
        yield Done(
            insights=cached_insights,
            recommendations=cached_recommendations,
            analyst_status="cached",
            coach_status="cached",
        )
        return

    # ------------------------------------------------------------------
    # Analyst phase
    # ------------------------------------------------------------------
    yield PhaseStart(phase="analyst")
    window_start = now_utc - timedelta(days=_ACTIVITY_WINDOW_DAYS)
    activities = await firestore.list_activities_in_range(
        uid, start=window_start, end=now_utc, limit=_ACTIVITY_FETCH_LIMIT
    )
    analyst_outcome = await analyst.generate_insights(
        activities=activities, user_id=uid, now=now_utc
    )

    if analyst_outcome.status == "empty":
        yield PhaseComplete(phase="analyst", status="empty", reason=analyst_outcome.reason)
        yield PhaseStart(phase="coach")
        yield PhaseComplete(phase="coach", status="skipped", reason=_COACH_SKIPPED_REASON)
        await firestore.set_generation_state(
            uid,
            GenerationState(
                uid=uid,
                last_completed_at=now_utc,
                analyst_status="empty",
                coach_status="skipped",
                empty_reason=analyst_outcome.reason,
            ),
        )
        yield Done(insights=[], recommendations=[], analyst_status="empty", coach_status="skipped")
        return

    if analyst_outcome.status == "failed":
        _logger.error("orchestrator.analyst_failed", uid=uid, reason=analyst_outcome.reason)
        yield PhaseComplete(phase="analyst", status="failed", reason=_ANALYST_FAILED_MESSAGE)
        yield PhaseStart(phase="coach")
        yield PhaseComplete(phase="coach", status="skipped", reason=_COACH_SKIPPED_REASON)
        await firestore.set_generation_state(
            uid,
            GenerationState(
                uid=uid,
                last_completed_at=now_utc,
                analyst_status="failed",
                coach_status="skipped",
                failed_reason=_ANALYST_FAILED_MESSAGE,
            ),
        )
        yield Done(insights=[], recommendations=[], analyst_status="failed", coach_status="skipped")
        return

    # analyst_outcome.status == "success"
    insights = analyst_outcome.insights
    if insights:
        analyst_reasoning = insights[0].agent_reasoning
        if analyst_reasoning is not None:
            for step in analyst_reasoning.reasoning_steps:
                yield ReasoningStep(phase="analyst", step=step)
    yield PhaseComplete(phase="analyst", status="success")
    for insight in insights:
        await firestore.add_insight(insight)

    # ------------------------------------------------------------------
    # Coach phase
    # ------------------------------------------------------------------
    yield PhaseStart(phase="coach")
    coach_outcome = await coach.generate_recommendations(
        profile=profile,
        activities=activities,
        insights=insights,
        user_id=uid,
        now=now_utc,
    )

    recommendations: list[Recommendation] = []
    coach_status: Literal["success", "empty", "failed"]
    empty_reason: str | None = None
    failed_reason: str | None = None

    if coach_outcome.status == "success":
        recommendations = coach_outcome.recommendations
        if recommendations:
            coach_reasoning = recommendations[0].agent_reasoning
            if coach_reasoning is not None:
                for step in coach_reasoning.reasoning_steps:
                    yield ReasoningStep(phase="coach", step=step)
        yield PhaseComplete(phase="coach", status="success")
        for rec in recommendations:
            await firestore.add_recommendation(rec)
        coach_status = "success"
    elif coach_outcome.status == "empty":
        yield PhaseComplete(phase="coach", status="empty", reason=coach_outcome.reason)
        coach_status = "empty"
        empty_reason = coach_outcome.reason
    else:  # coach_outcome.status == "failed"
        _logger.error("orchestrator.coach_failed", uid=uid, reason=coach_outcome.reason)
        yield PhaseComplete(phase="coach", status="failed", reason=_COACH_FAILED_MESSAGE)
        coach_status = "failed"
        failed_reason = _COACH_FAILED_MESSAGE

    await firestore.set_generation_state(
        uid,
        GenerationState(
            uid=uid,
            last_completed_at=now_utc,
            analyst_status="success",
            coach_status=coach_status,
            empty_reason=empty_reason,
            failed_reason=failed_reason,
        ),
    )
    yield Done(
        insights=insights,
        recommendations=recommendations,
        analyst_status="success",
        coach_status=coach_status,
    )
