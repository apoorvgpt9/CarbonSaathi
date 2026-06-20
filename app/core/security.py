"""Security headers middleware for CarbonSaathi.

Registers an HTTP middleware that applies a strict, hand-crafted set of
security response headers to every response.  Unlike
:meth:`secure.Secure.with_default_headers`, the CSP here is tailored to the
Phase 6 frontend: it whitelists the three CDNs we load (Tailwind, HTMX,
Firebase via gstatic), allows the Firebase Identity Toolkit / token endpoints
in ``connect-src``, and permits the Firebase auth-handler popup in
``frame-src``.

Critical invariants:
    * ``script-src`` does NOT contain ``'unsafe-inline'`` — every script we
      ship is an external file or a CDN URL.  Inline ``<script>`` blocks are
      forbidden by the Phase 6 spec.
    * ``style-src`` DOES contain ``'unsafe-inline'`` because the Tailwind CDN
      injects ``<style>`` tags at runtime.  Removing this would break Tailwind
      utility classes and is only avoidable with a build step.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import secure
from fastapi import FastAPI, Request
from starlette.responses import Response

from app.core.config import get_settings


def _build_csp() -> secure.ContentSecurityPolicy:
    """Construct the application's Content-Security-Policy.

    Returns:
        A :class:`secure.ContentSecurityPolicy` configured for the Phase 6
        frontend.  The ``frame-src`` host is derived from
        ``settings.firebase_auth_domain`` so non-production projects work
        without code edits.
    """
    auth_domain = get_settings().firebase_auth_domain
    return (
        secure.ContentSecurityPolicy()
        .default_src("'self'")
        .script_src(
            "'self'",
            "https://cdn.tailwindcss.com",
            "https://unpkg.com",
            "https://www.gstatic.com",
        )
        .style_src("'self'", "'unsafe-inline'", "https://cdn.tailwindcss.com")
        .img_src("'self'", "data:", "https:")
        .font_src("'self'", "data:")
        .connect_src(
            "'self'",
            "https://*.googleapis.com",
            "https://securetoken.googleapis.com",
            "https://identitytoolkit.googleapis.com",
        )
        .frame_src(f"https://{auth_domain}")
        .base_uri("'self'")
        .form_action("'self'")
        .frame_ancestors("'none'")
        .object_src("'none'")
    )


def _build_secure_headers() -> secure.Secure:
    """Construct the :class:`secure.Secure` instance applied to every response.

    Returns:
        A configured :class:`secure.Secure` with custom CSP plus standard
        hardening headers (HSTS, X-Content-Type-Options, X-Frame-Options,
        Referrer-Policy, Permissions-Policy).
    """
    return secure.Secure(
        csp=_build_csp(),
        hsts=secure.StrictTransportSecurity().max_age(31_536_000).include_subdomains(),
        xcto=secure.XContentTypeOptions(),
        xfo=secure.XFrameOptions().deny(),
        referrer=secure.ReferrerPolicy().strict_origin_when_cross_origin(),
        permissions=secure.PermissionsPolicy().geolocation().microphone().camera(),
    )


def configure_security_middleware(app: FastAPI) -> None:
    """Register the security-headers middleware on ``app``.

    Args:
        app: The FastAPI application to attach the middleware to.

    Returns:
        None.
    """
    secure_headers = _build_secure_headers()

    @app.middleware("http")
    async def _set_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        secure_headers.set_headers(response)
        return response
