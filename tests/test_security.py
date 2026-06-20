"""Tests for security-headers middleware.

Verifies the custom Phase 6 CSP plus the standard hardening headers
(X-Content-Type-Options, X-Frame-Options, HSTS, Referrer-Policy,
Permissions-Policy).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest


@pytest.fixture()
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Provide an async ASGI test client for the full application."""
    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.asyncio
async def test_security_headers_present(client: httpx.AsyncClient) -> None:
    """Standard hardening headers are emitted on every response."""
    response = await client.get("/api/health")
    headers = {key.lower(): value for key, value in response.headers.items()}
    assert headers["x-content-type-options"] == "nosniff"
    assert "x-frame-options" in headers
    assert "referrer-policy" in headers
    assert "strict-transport-security" in headers
    assert "permissions-policy" in headers


@pytest.mark.asyncio
async def test_csp_present(client: httpx.AsyncClient) -> None:
    """A Content-Security-Policy header is emitted."""
    response = await client.get("/api/health")
    assert "content-security-policy" in {k.lower() for k in response.headers}


@pytest.mark.asyncio
async def test_csp_whitelists_required_cdns(client: httpx.AsyncClient) -> None:
    """The CSP allows the three CDNs Phase 6 loads (Tailwind, HTMX, Firebase)."""
    response = await client.get("/api/health")
    csp = response.headers["content-security-policy"]
    assert "https://cdn.tailwindcss.com" in csp
    assert "https://unpkg.com" in csp
    assert "https://www.gstatic.com" in csp


@pytest.mark.asyncio
async def test_csp_allows_firebase_connect_targets(client: httpx.AsyncClient) -> None:
    """connect-src permits the Firebase identity-toolkit endpoints used by sign-in."""
    response = await client.get("/api/health")
    csp = response.headers["content-security-policy"]
    assert "https://*.googleapis.com" in csp
    assert "https://securetoken.googleapis.com" in csp
    assert "https://identitytoolkit.googleapis.com" in csp


@pytest.mark.asyncio
async def test_csp_script_src_has_no_unsafe_inline(client: httpx.AsyncClient) -> None:
    """script-src must NOT contain 'unsafe-inline' — Phase 6 forbids inline scripts."""
    response = await client.get("/api/health")
    csp = response.headers["content-security-policy"]
    script_directive = next(
        (d for d in csp.split(";") if d.strip().startswith("script-src ")),
        "",
    )
    assert script_directive != ""
    assert "'unsafe-inline'" not in script_directive


@pytest.mark.asyncio
async def test_csp_style_src_has_unsafe_inline(client: httpx.AsyncClient) -> None:
    """style-src DOES contain 'unsafe-inline' — required for Tailwind CDN runtime."""
    response = await client.get("/api/health")
    csp = response.headers["content-security-policy"]
    style_directive = next(
        (d for d in csp.split(";") if d.strip().startswith("style-src ")),
        "",
    )
    assert style_directive != ""
    assert "'unsafe-inline'" in style_directive


@pytest.mark.asyncio
async def test_csp_frame_src_uses_configured_auth_domain(client: httpx.AsyncClient) -> None:
    """frame-src is derived from settings.firebase_auth_domain (test value)."""
    response = await client.get("/api/health")
    csp = response.headers["content-security-policy"]
    assert "https://test.firebaseapp.com" in csp


@pytest.mark.asyncio
async def test_csp_locks_down_dangerous_directives(client: httpx.AsyncClient) -> None:
    """frame-ancestors and object-src are 'none'; base-uri/form-action are 'self'."""
    response = await client.get("/api/health")
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp
