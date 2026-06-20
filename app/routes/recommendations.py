"""Recommendation routes for CarbonSaathi.

Provides the read-only recommendation lister and the accept mutation.  All
generation happens via ``GET /api/insights/stream``; these endpoints never
invoke an agent.

Routes
------
- ``GET  /api/recommendations`` — latest persisted recommendations (read-only)
- ``POST /api/recommendations/{rec_id}/accept`` — mark a recommendation accepted
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import CurrentUser, verify_firebase_token
from app.models.recommendation import Recommendation
from app.services.firestore_service import FirestoreService, get_firestore_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

_RECENT_LIMIT = 10
"""Maximum number of cached recommendations returned by the read-only lister."""


class RecommendationListResponse(BaseModel):
    """Read-only list of the user's latest recommendations.

    Attributes:
        items: Recommendations ordered by ``generated_at`` descending.
    """

    items: list[Recommendation]


class AcceptResponse(BaseModel):
    """Result of accepting a recommendation.

    Attributes:
        accepted: Always ``True`` on success.
        rec_id: The accepted recommendation's ID.
    """

    accepted: bool
    rec_id: str


@router.get(
    "",
    response_model=RecommendationListResponse,
    summary="List latest recommendations",
)
async def list_recommendations(
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
) -> RecommendationListResponse:
    """Return the user's most recently persisted recommendations (no generation).

    Args:
        current: The authenticated Firebase user.
        service: The Firestore persistence layer.

    Returns:
        A :class:`RecommendationListResponse`; ``items`` is empty (HTTP 200,
        never 404) when nothing has been generated yet.
    """
    recommendations = await service.get_recent_recommendations(current.uid, limit=_RECENT_LIMIT)
    return RecommendationListResponse(items=recommendations)


@router.post(
    "/{rec_id}/accept",
    response_model=AcceptResponse,
    summary="Accept a recommendation",
)
async def accept_recommendation(
    rec_id: str,
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
) -> AcceptResponse:
    """Mark a recommendation as accepted.

    Returns 404 with the same message whether the recommendation does not exist
    or is owned by another user — recommendations are path-scoped under the
    caller's UID, so ownership is never leaked.

    Args:
        rec_id: Firestore document ID of the recommendation.
        current: The authenticated Firebase user.
        service: The Firestore persistence layer.

    Returns:
        An :class:`AcceptResponse` on success.

    Raises:
        HTTPException: 404 if the recommendation is not found for this user.
    """
    updated = await service.accept_recommendation(current.uid, rec_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return AcceptResponse(accepted=True, rec_id=rec_id)
