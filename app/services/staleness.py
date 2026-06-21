"""Staleness evaluation for CarbonSaathi's insight-generation pipeline.

Exposes :func:`is_pipeline_stale`, which decides whether the Analyst -> Coach
pipeline must regenerate or whether the previously persisted insights and
recommendations may be served from cache.  The function is pure with respect to
FastAPI: it depends only on the injected
:class:`~app.services.firestore_service.FirestoreService` and an explicit
``now_utc`` reference, so every branch is independently unit-testable.

The IST constant is duplicated locally (rather than imported from a route
module) per DECISIONS.md § 14.5; introduce ``app/core/timezones.py`` only when a
third caller appears.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from app.models.generation_state import GenerationState
from app.services.firestore_service import FirestoreService

IST = ZoneInfo("Asia/Kolkata")  # DECISIONS.md § 14.5

_EMPTY_TTL = timedelta(minutes=10)
"""How long an empty pipeline result is cached before a forced regeneration."""


class StalenessResult(BaseModel):
    """Outcome of a staleness evaluation.

    Attributes:
        stale: ``True`` when the pipeline must regenerate.
        reason: Machine-readable code explaining the decision.
        cached_state: The persisted
            :class:`~app.models.generation_state.GenerationState`, or ``None``
            when no prior run exists.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stale: bool
    reason: str
    cached_state: GenerationState | None


async def is_pipeline_stale(
    *,
    uid: str,
    firestore: FirestoreService,
    now_utc: datetime,
) -> StalenessResult:
    """Decide whether the insight pipeline must regenerate for a user.

    The pipeline is stale (must regenerate) when any of the following hold,
    evaluated in order:

    1. No :class:`~app.models.generation_state.GenerationState` exists
       (``"no_prior_run"``).
    2. The previous run failed — either ``analyst_status`` or ``coach_status``
       is ``"failed"`` (``"previous_run_failed"``).  A failed run produces no
       usable cache; the next request retries unconditionally.
    3. The last run completed on a different IST calendar day
       (``"ist_day_change"``).
    4. An activity has been logged since the last run completed
       (``"new_activity_since_last_run"``).
    5. The Analyst was empty and the empty-result TTL has expired
       (``"analyst_empty_ttl_expired"``).
    6. The Coach was empty and the empty-result TTL has expired
       (``"coach_empty_ttl_expired"``).

    Otherwise the cached result may be served (``"fresh"``).

    Args:
        uid: Firebase UID of the user.
        firestore: Persistence layer used to read prior state and activities.
        now_utc: Reference time (UTC, timezone-aware) for every comparison.

    Returns:
        A :class:`StalenessResult` carrying the decision, a reason code, and the
        cached state when one exists.
    """
    state = await firestore.get_generation_state(uid)
    if state is None:
        return StalenessResult(stale=True, reason="no_prior_run", cached_state=None)

    if state.analyst_status == "failed" or state.coach_status == "failed":
        return StalenessResult(stale=True, reason="previous_run_failed", cached_state=state)

    today_ist = now_utc.astimezone(IST).date()
    cached_ist = state.last_completed_at.astimezone(IST).date()
    if today_ist != cached_ist:
        return StalenessResult(stale=True, reason="ist_day_change", cached_state=state)

    latest = await firestore.list_activities(uid, limit=1)
    if latest and latest[0].timestamp > state.last_completed_at:
        return StalenessResult(stale=True, reason="new_activity_since_last_run", cached_state=state)

    age = now_utc - state.last_completed_at
    if state.analyst_status == "empty" and age > _EMPTY_TTL:
        return StalenessResult(stale=True, reason="analyst_empty_ttl_expired", cached_state=state)
    if state.coach_status == "empty" and age > _EMPTY_TTL:
        return StalenessResult(stale=True, reason="coach_empty_ttl_expired", cached_state=state)

    return StalenessResult(stale=False, reason="fresh", cached_state=state)
