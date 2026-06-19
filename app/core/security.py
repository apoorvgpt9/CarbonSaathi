"""Security headers middleware for CarbonSaathi.

Registers an HTTP middleware that applies a secure set of default response
headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
Permissions-Policy) to every response using the ``secure`` library.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import secure
from fastapi import FastAPI, Request
from starlette.responses import Response

_secure_headers = secure.Secure.with_default_headers()


def configure_security_middleware(app: FastAPI) -> None:
    """Register the security-headers middleware on ``app``.

    Args:
        app: The FastAPI application to attach the middleware to.

    Returns:
        None.
    """

    @app.middleware("http")
    async def _set_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        _secure_headers.set_headers(response)
        return response
