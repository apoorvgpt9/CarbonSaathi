"""Firebase ID token verification dependency for CarbonSaathi.

Exposes :class:`CurrentUser` and the :func:`verify_firebase_token` FastAPI
dependency.  Every authentication failure is mapped to HTTP 401 with the opaque
client message ``"Authentication failed"``; the specific cause is recorded only
in structured logs, never returned to the caller.  Auth therefore never raises a
500 and never leaks an exception class to the client.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import Header, HTTPException, Request, status
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel, ConfigDict

from app.core.firebase import get_firebase_app

_logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_BEARER_PREFIX = "bearer "
"""Lower-cased Authorization scheme prefix expected before the ID token."""

_UNAUTHORIZED_DETAIL = "Authentication failed"
"""Opaque client-facing message used for every authentication failure."""


class CurrentUser(BaseModel):
    """Authenticated caller derived from a verified Firebase ID token.

    Attributes:
        uid: Firebase Authentication UID (stable primary key).
        email: Email claim, if present on the token.
        email_verified: Whether Firebase reports the email as verified.
        name: Display-name claim, if present on the token.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    uid: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None


def _unauthorized() -> HTTPException:
    """Build the standard 401 error with the opaque client message.

    Returns:
        An :class:`fastapi.HTTPException` with status 401 and a detail that
        never reveals the underlying cause.
    """
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_DETAIL)


async def verify_firebase_token(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> CurrentUser:
    """Verify the bearer Firebase ID token and return the current user.

    On success the resolved :class:`CurrentUser` is also attached to
    ``request.state.user`` so the rate-limit key function
    (:func:`app.core.ratelimit.key_uid_or_ip`) can read the uid when slowapi's
    per-route ``@limiter.limit(...)`` decorator runs inside the route.

    Args:
        request: The incoming request — :class:`Request` is auto-injected by
            FastAPI's dependency machinery.
        authorization: Raw ``Authorization`` request header. Expected to be of
            the form ``"Bearer <id_token>"`` (the scheme is matched
            case-insensitively).

    Returns:
        The :class:`CurrentUser` parsed from the verified token claims.

    Raises:
        HTTPException: Always status 401 with detail ``"Authentication failed"``
            when the header is missing or malformed, or when the token cannot be
            verified.  The specific cause is logged, never returned to the
            client.
    """
    if authorization is None or not authorization.lower().startswith(_BEARER_PREFIX):
        _logger.warning("auth.malformed_header")
        raise _unauthorized()
    token = authorization[len(_BEARER_PREFIX) :].strip()
    if not token:
        _logger.warning("auth.malformed_header")
        raise _unauthorized()

    try:
        decoded: dict[str, Any] = firebase_auth.verify_id_token(
            token, app=get_firebase_app(), check_revoked=True
        )
    except firebase_auth.ExpiredIdTokenError:
        _logger.warning("auth.expired_token")
        raise _unauthorized() from None
    except firebase_auth.RevokedIdTokenError:
        _logger.warning("auth.revoked_token")
        raise _unauthorized() from None
    except firebase_auth.InvalidIdTokenError:
        _logger.warning("auth.invalid_token")
        raise _unauthorized() from None
    except firebase_auth.CertificateFetchError:
        _logger.warning("auth.cert_fetch_failed")
        raise _unauthorized() from None
    except ValueError:
        _logger.warning("auth.value_error")
        raise _unauthorized() from None
    except Exception:
        # Catch-all: auth must never surface a 500 or leak details to the client.
        _logger.error("auth.unexpected_error")
        raise _unauthorized() from None

    user = CurrentUser(
        uid=decoded["uid"],
        email=decoded.get("email"),
        email_verified=decoded.get("email_verified", False),
        name=decoded.get("name"),
    )
    request.state.user = user
    return user
