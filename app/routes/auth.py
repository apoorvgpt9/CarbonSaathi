"""Authentication routes for CarbonSaathi.

Exposes ``POST /api/auth/verify``, which verifies the caller's Firebase ID token
(via the :func:`~app.core.auth.verify_firebase_token` dependency) and ensures a
:class:`~app.models.user.UserProfile` exists for them.  First-time callers get a
minimal, not-yet-onboarded profile; returning callers have their ``last_active``
timestamp refreshed in the background.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.core.auth import CurrentUser, verify_firebase_token
from app.models.user import UserProfile
from app.services.firestore_service import (
    FirestoreService,
    fire_and_forget,
    get_firestore_service,
)

router = APIRouter(tags=["auth"])


class VerifyResponse(BaseModel):
    """Response body for ``POST /api/auth/verify``.

    Attributes:
        user: The persisted user profile (created on first sign-in).
        is_new: ``True`` when this call created the profile, ``False`` when an
            existing profile was found and its ``last_active`` refreshed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    user: UserProfile
    is_new: bool


def _display_name(current: CurrentUser) -> str:
    """Derive a display name from the verified token claims.

    Args:
        current: The authenticated caller.

    Returns:
        The ``name`` claim when present; otherwise the email local-part; and
        finally ``"User"`` when neither is available.
    """
    if current.name:
        return current.name
    if current.email:
        return current.email.split("@")[0]
    return "User"


@router.post("/auth/verify")
async def verify(
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
) -> VerifyResponse:
    """Verify the caller and ensure a user profile exists.

    On first sign-in a minimal, not-yet-onboarded profile is created and
    persisted synchronously.  On subsequent calls the existing profile's
    ``last_active`` timestamp is refreshed with a fire-and-forget write so the
    response is not blocked.

    Args:
        current: The authenticated caller, injected by the auth dependency.
        service: The Firestore service, injected by dependency.

    Returns:
        A :class:`VerifyResponse` carrying the profile and whether it is new.
    """
    now = datetime.now(tz=UTC)
    existing = await service.get_user(current.uid)
    if existing is None:
        profile = UserProfile(
            uid=current.uid,
            email=current.email,
            display_name=_display_name(current),
            state=None,
            home_profile=None,
            created_at=now,
            last_active=now,
            onboarding_complete=False,
        )
        await service.upsert_user(profile)
        return VerifyResponse(user=profile, is_new=True)

    updated = existing.model_copy(update={"last_active": now})
    fire_and_forget(service.upsert_user(updated))
    return VerifyResponse(user=updated, is_new=False)
