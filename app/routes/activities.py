"""Activity routes for CarbonSaathi.

Provides endpoints for logging new activities via the :class:`LoggerAgent`
(natural-language → structured carbon record) and for retrieving activity
history.

Routes
------
- ``POST /api/activities`` — log a new activity in natural language
- ``GET  /api/activities`` — paginated list of recent activities
- ``GET  /api/activities/{activity_id}`` — single activity detail
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from app.agents.factories import get_logger_agent
from app.agents.logger_agent import LoggerAgent
from app.core.auth import CurrentUser, verify_firebase_token
from app.core.ratelimit import limiter
from app.models.activity import Activity
from app.models.shared import AgentReasoning
from app.models.user import IndianState
from app.services.firestore_service import FirestoreService, get_firestore_service

router = APIRouter(prefix="/activities", tags=["activities"])

_logger = structlog.get_logger(__name__)

# Fallback state used when the user has not completed onboarding and therefore
# has no stored IndianState.  Maharashtra is the closest proxy for a national
# urban-metro average grid emission factor.
_DEFAULT_STATE: IndianState = IndianState.MAHARASHTRA


class LogActivityRequest(BaseModel):
    """Request body for POST /api/activities.

    Attributes:
        raw_input: Free-text description of the activity (1-500 chars, stripped).
    """

    raw_input: Annotated[
        str,
        StringConstraints(min_length=1, max_length=500, strip_whitespace=True),
    ]


class LogActivityResponse(BaseModel):
    """Response body for a successfully logged activity.

    Attributes:
        activity: The persisted :class:`~app.models.activity.Activity`.
        agent_reasoning: Reasoning trace produced by the Logger agent.
    """

    activity: Activity
    agent_reasoning: AgentReasoning | None


class ActivityListResponse(BaseModel):
    """Paginated list of activities.

    Attributes:
        items: Activities ordered by timestamp descending.
        next_cursor: ISO-8601 timestamp to pass as ``before`` for the next
            page; ``None`` when there are no further results.
    """

    items: list[Activity]
    next_cursor: str | None


@router.post(
    "",
    response_model=LogActivityResponse,
    status_code=201,
    summary="Log a new carbon activity",
)
@limiter.limit("30/minute")
async def log_activity(
    request: Request,
    req: LogActivityRequest,
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
    logger_agent: Annotated[LoggerAgent, Depends(get_logger_agent)],
) -> LogActivityResponse:
    """Convert a natural-language description into a stored carbon activity.

    Calls the :class:`~app.agents.logger_agent.LoggerAgent` to parse and
    validate the input, then persists the result via
    :class:`~app.services.firestore_service.FirestoreService`.

    Args:
        request: Incoming request (used by the rate limiter).
        req: The parsed request body.
        current: The authenticated Firebase user.
        service: The Firestore persistence layer.
        logger_agent: The logger agent singleton.

    Returns:
        A :class:`LogActivityResponse` on success.

    Raises:
        HTTPException: 400 if governance rejects the input; 500 on agent failure.
    """
    # Fetch user profile to obtain their registered state for the electricity
    # grid emission factor.  Fall back to Maharashtra (national urban average)
    # if the user has not completed onboarding yet.
    profile = await service.get_user(current.uid)
    user_state: IndianState = (
        profile.state if (profile is not None and profile.state is not None) else _DEFAULT_STATE
    )

    activity_id = str(uuid.uuid4())

    outcome = await logger_agent.log_activity(
        user_input=req.raw_input,
        user_state=user_state,
        activity_id=activity_id,
        user_id=current.uid,
        now=datetime.now(UTC),
    )

    if outcome.status == "success":
        await service.add_activity(outcome.activity)
        return LogActivityResponse(
            activity=outcome.activity,
            agent_reasoning=outcome.activity.agent_reasoning,
        )

    if outcome.status == "rejected":
        return JSONResponse(  # type: ignore[return-value]
            status_code=400,
            content={
                "detail": "Could not log activity",
                "reason": outcome.reason,
                "category": outcome.category,
            },
        )

    # status == "failed"
    _logger.error(
        "activity.log_failed",
        reason=outcome.reason,
        user_id=current.uid,
    )
    return JSONResponse(  # type: ignore[return-value]
        status_code=500,
        content={"detail": "Could not log activity"},
    )


@router.get(
    "",
    response_model=ActivityListResponse,
    summary="List recent activities",
)
@limiter.limit("60/minute")
async def list_activities(
    request: Request,
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
    limit: int = Query(20, ge=1, le=50),
    before: datetime | None = Query(None),  # noqa: B008
) -> ActivityListResponse:
    """Return a page of the user's most recent activities.

    Args:
        request: Incoming request (used by the rate limiter).
        current: The authenticated Firebase user.
        service: The Firestore persistence layer.
        limit: Maximum number of items per page (1-50, default 20).
        before: Cursor — only activities strictly before this UTC timestamp
            are returned.  Pass the previous response's ``next_cursor`` value.

    Returns:
        An :class:`ActivityListResponse` with items and optional cursor.
    """
    results = await service.list_activities(current.uid, limit=limit, before=before)
    next_cursor: str | None = results[-1].timestamp.isoformat() if len(results) == limit else None
    return ActivityListResponse(items=results, next_cursor=next_cursor)


@router.get(
    "/{activity_id}",
    response_model=Activity,
    summary="Get a single activity",
)
async def get_activity(
    activity_id: str,
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
) -> Activity:
    """Retrieve a single activity by ID, scoped to the authenticated user.

    Returns 404 regardless of whether the activity does not exist or isclear
    owned by a different user to avoid information leakage.

    Args:
        activity_id: Firestore document ID of the activity.
        current: The authenticated Firebase user.
        service: The Firestore persistence layer.

    Returns:
        The :class:`~app.models.activity.Activity` if found.

    Raises:
        HTTPException: 404 if the activity is not found or not owned by the
            current user.
    """
    activity = await service.get_activity(current.uid, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity
