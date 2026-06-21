"""User profile routes for CarbonSaathi.

Exposes ``GET /api/users/me`` (return the caller's profile) and
``POST /api/users/onboarding`` (set the caller's state and home profile and mark
onboarding complete).  Both depend on the
:func:`~app.core.auth.verify_firebase_token` dependency and the Firestore
service.  The caller must already have a profile (created by
``POST /api/auth/verify``) before onboarding.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.core.auth import CurrentUser, verify_firebase_token
from app.core.ratelimit import limiter
from app.models.user import HomeProfile, IndianState, UserProfile
from app.services.firestore_service import FirestoreService, get_firestore_service

router = APIRouter(prefix="/users", tags=["users"])

_PROFILE_NOT_FOUND = "User profile not found"
"""Detail message returned when the caller has no persisted profile."""


class OnboardingPayload(BaseModel):
    """Request body for ``POST /api/users/onboarding``.

    Attributes:
        state: The user's Indian state, selecting the CEA grid factor.
        home_profile: The user's home attributes for estimation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: IndianState
    home_profile: HomeProfile


@router.get("/me")
@limiter.limit("60/minute")
async def get_me(
    request: Request,
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
) -> UserProfile:
    """Return the authenticated user's profile.

    Args:
        request: Incoming request (used by the rate limiter).
        current: The authenticated caller, injected by the auth dependency.
        service: The Firestore service, injected by dependency.

    Returns:
        The caller's :class:`~app.models.user.UserProfile`.

    Raises:
        HTTPException: 404 when no profile exists for the caller.
    """
    profile = await service.get_user(current.uid)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PROFILE_NOT_FOUND)
    return profile


@router.post("/onboarding")
@limiter.limit("30/minute")
async def onboarding(
    request: Request,
    payload: OnboardingPayload,
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
) -> UserProfile:
    """Set the caller's state and home profile and mark onboarding complete.

    The caller must already have a profile (created by ``/api/auth/verify``).
    Re-onboarding an already-onboarded user is allowed and treated as an update.

    Args:
        request: Incoming request (used by the rate limiter).
        payload: The onboarding fields (state and home profile).
        current: The authenticated caller, injected by the auth dependency.
        service: The Firestore service, injected by dependency.

    Returns:
        The updated :class:`~app.models.user.UserProfile`.

    Raises:
        HTTPException: 404 when the caller has no profile yet.
    """
    existing = await service.get_user(current.uid)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PROFILE_NOT_FOUND)
    updated = existing.model_copy(
        update={
            "state": payload.state,
            "home_profile": payload.home_profile,
            "onboarding_complete": True,
            "last_active": datetime.now(tz=UTC),
        }
    )
    await service.upsert_user(updated)
    return updated
