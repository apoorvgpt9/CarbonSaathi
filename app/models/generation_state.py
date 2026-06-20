"""GenerationState model for CarbonSaathi's insight pipeline.

A single :class:`GenerationState` document per user, stored at
``users/{uid}/state/generation`` in Firestore, records the outcome of the most
recent Analyst -> Coach run.  It drives the staleness and empty-result caching
logic in :mod:`app.services.staleness` and is written only by the
insight-generation orchestrator after a non-cached run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.shared import IsoTimestamp


class GenerationState(BaseModel):
    """Outcome record of the most recent insight-pipeline run for a user.

    Attributes:
        uid: Firebase UID of the owning user.
        last_completed_at: When the run finished (UTC, timezone-aware).
        analyst_status: Terminal status of the Analyst phase.
        coach_status: Terminal status of the Coach phase; ``"skipped"`` when the
            Analyst produced no insights and the Coach was not run.
        empty_reason: Human-readable explanation when either phase was empty;
            ``None`` otherwise.
        failed_reason: Safe (non-exception) explanation when either phase
            failed; ``None`` otherwise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    uid: str
    last_completed_at: IsoTimestamp
    analyst_status: Literal["success", "empty", "failed"]
    coach_status: Literal["success", "empty", "failed", "skipped"]
    empty_reason: str | None = None
    failed_reason: str | None = None
