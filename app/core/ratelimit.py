"""Rate-limit configuration for CarbonSaathi.

Exposes the single :class:`slowapi.Limiter` instance used by the FastAPI app
plus the :func:`key_uid_or_ip` key function.

Strategy:
    * For authenticated routes, the per-uid bucket is the right granularity —
      a single user can't exhaust the budget for others sharing the same NAT
      IP, and one user can't be DoS'd by their neighbours.
    * For unauthenticated or pre-auth routes (``/api/health``,
      ``/api/auth/config``, the HTML pages, ``POST /api/auth/verify``) we fall
      back to ``get_remote_address`` since there is no uid to key on.

``key_uid_or_ip`` reads ``request.state.user`` (populated by
:func:`app.core.auth.verify_firebase_token`).  When :class:`SlowAPIMiddleware`
runs the global default limit *before* dependency resolution, ``state.user``
is unset and the function falls back to IP keying.  Per-route
``@limiter.limit(...)`` decorators run *inside* the route after dependencies
have resolved, by which point ``state.user`` is populated and per-uid keying
takes effect.

Tests disable the limiter wholesale by setting ``limiter.enabled = False`` in
``tests/conftest.py``; the dedicated rate-limit tests re-enable it under a
fixture.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings


def key_uid_or_ip(request: Request) -> str:
    """Return the rate-limit bucket key for ``request``.

    Args:
        request: The incoming request.

    Returns:
        ``"uid:<firebase-uid>"`` when an authenticated user has been attached
        to ``request.state.user`` by the auth dependency, otherwise
        ``"ip:<remote-address>"`` from :func:`slowapi.util.get_remote_address`.
    """
    user = getattr(request.state, "user", None)
    if user is not None:
        return f"uid:{user.uid}"
    return f"ip:{get_remote_address(request)}"


_settings = get_settings()
limiter = Limiter(
    key_func=key_uid_or_ip,
    default_limits=[f"{_settings.rate_limit_per_minute}/minute"],
)
"""The global :class:`Limiter` instance shared by every route decorator and
the :class:`SlowAPIMiddleware` registration in :func:`app.main.create_app`."""
