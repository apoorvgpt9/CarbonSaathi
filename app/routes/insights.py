"""Insight routes for CarbonSaathi.

Provides the read-only insight lister and the Analyst -> Coach generation
stream that powers the visible-reasoning UI differentiator.  The stream endpoint
is the *only* path that invokes the agents; :func:`list_insights` simply serves
the last persisted result.

Routes
------
- ``GET /api/insights`` — latest persisted insights (read-only)
- ``GET /api/insights/stream`` — run the pipeline (SSE or JSON, negotiated)
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.responses import Response

from app.agents.analyst_agent import AnalystAgent
from app.agents.coach_agent import CoachAgent
from app.agents.factories import get_analyst_agent, get_coach_agent
from app.core.auth import CurrentUser, verify_firebase_token
from app.models.insight import Insight
from app.models.user import UserProfile
from app.services.firestore_service import FirestoreService, get_firestore_service
from app.services.orchestrator import Done, run_insight_pipeline

router = APIRouter(prefix="/insights", tags=["insights"])

_logger = structlog.get_logger(__name__)

SSE_INTER_EVENT_DELAY_S = 0.08
"""Seconds to pause between streamed events (tests patch this to ``0``)."""

_RECENT_LIMIT = 10
"""Maximum number of cached insights returned by the read-only lister."""


class InsightListResponse(BaseModel):
    """Read-only list of the user's latest insights.

    Attributes:
        items: Insights ordered by ``generated_at`` descending.
    """

    items: list[Insight]


@router.get("", response_model=InsightListResponse, summary="List latest insights")
async def list_insights(
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
) -> InsightListResponse:
    """Return the user's most recently persisted insights (no generation).

    Args:
        current: The authenticated Firebase user.
        service: The Firestore persistence layer.

    Returns:
        An :class:`InsightListResponse`; ``items`` is empty (HTTP 200, never
        404) when nothing has been generated yet.
    """
    insights = await service.get_recent_insights(current.uid, limit=_RECENT_LIMIT)
    return InsightListResponse(items=insights)


@router.get("/stream", summary="Generate insights and recommendations")
async def stream_insights(
    request: Request,
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
    analyst: Annotated[AnalystAgent, Depends(get_analyst_agent)],
    coach: Annotated[CoachAgent, Depends(get_coach_agent)],
) -> Response:
    """Run the Analyst -> Coach pipeline, negotiating SSE vs JSON on ``Accept``.

    ``Accept: application/json`` (without ``text/event-stream``) returns a single
    JSON ``done`` payload after the pipeline completes.  Every other ``Accept``
    value — none, ``*/*``, ``text/event-stream``, or both types together —
    streams Server-Sent Events with a short inter-event delay.

    Args:
        request: The incoming request (read for its ``Accept`` header).
        current: The authenticated Firebase user.
        service: The Firestore persistence layer.
        analyst: The Analyst agent singleton.
        coach: The Coach agent singleton.

    Returns:
        A :class:`~starlette.responses.StreamingResponse` (SSE) or
        :class:`~fastapi.responses.JSONResponse`, depending on ``Accept``.

    Raises:
        HTTPException: 500 when the user profile is missing (a Phase 5A contract
            violation).
    """
    profile = await service.get_user(current.uid)
    if profile is None:
        _logger.error("route.profile_missing", uid=current.uid)
        raise HTTPException(status_code=500, detail="Server error")

    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/event-stream" not in accept:
        return await _run_pipeline_json(
            uid=current.uid, profile=profile, analyst=analyst, coach=coach, service=service
        )
    return StreamingResponse(
        _run_pipeline_sse(
            uid=current.uid, profile=profile, analyst=analyst, coach=coach, service=service
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _run_pipeline_sse(
    *,
    uid: str,
    profile: UserProfile,
    analyst: AnalystAgent,
    coach: CoachAgent,
    service: FirestoreService,
) -> AsyncIterator[str]:
    """Yield Server-Sent Event frames for each orchestrator event.

    Args:
        uid: Firebase UID of the user.
        profile: The user's profile.
        analyst: The Analyst agent.
        coach: The Coach agent.
        service: The Firestore persistence layer.

    Yields:
        SSE-framed strings (``event:``/``data:`` blocks). A short delay is
        inserted between events, except before the terminal ``done`` event.
    """
    async for event in run_insight_pipeline(
        uid=uid, profile=profile, analyst=analyst, coach=coach, firestore=service
    ):
        payload = event.model_dump(mode="json")
        yield f"event: {event.event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
        if event.event != "done":
            await asyncio.sleep(SSE_INTER_EVENT_DELAY_S)


async def _run_pipeline_json(
    *,
    uid: str,
    profile: UserProfile,
    analyst: AnalystAgent,
    coach: CoachAgent,
    service: FirestoreService,
) -> JSONResponse:
    """Run the pipeline to completion and return its terminal ``done`` payload.

    Args:
        uid: Firebase UID of the user.
        profile: The user's profile.
        analyst: The Analyst agent.
        coach: The Coach agent.
        service: The Firestore persistence layer.

    Returns:
        A :class:`~fastapi.responses.JSONResponse` carrying the serialized
        :class:`~app.services.orchestrator.Done` event.

    Raises:
        HTTPException: 500 if the pipeline never yields a ``done`` event.
    """
    done_event: Done | None = None
    async for event in run_insight_pipeline(
        uid=uid, profile=profile, analyst=analyst, coach=coach, firestore=service
    ):
        if isinstance(event, Done):
            done_event = event
    if done_event is None:
        _logger.error("route.pipeline_incomplete", uid=uid)
        raise HTTPException(status_code=500, detail="Pipeline did not complete")
    return JSONResponse(done_event.model_dump(mode="json"))
