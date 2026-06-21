"""Tests for security-headers middleware.

Verifies the custom Phase 6 CSP plus the standard hardening headers
(X-Content-Type-Options, X-Frame-Options, HSTS, Referrer-Policy,
Permissions-Policy).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

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
async def test_server_header_not_duplicated(client: httpx.AsyncClient) -> None:
    """Server header must not appear more than once.

    Uvicorn's "Server: uvicorn" is suppressed at the wire via
    ``--no-server-header`` in the Dockerfile / Makefile. The ASGI layer here
    only sees what middleware emits, so any duplication would come from
    ``secure`` itself; this test guards against that regression.
    """
    response = await client.get("/api/health")
    server_headers = response.headers.get_list("server")
    assert len(server_headers) <= 1, f"Multiple Server headers: {server_headers!r}"


@pytest.mark.asyncio
async def test_csp_present(client: httpx.AsyncClient) -> None:
    """A Content-Security-Policy header is emitted."""
    response = await client.get("/api/health")
    assert "content-security-policy" in {k.lower() for k in response.headers}


@pytest.mark.asyncio
async def test_csp_whitelists_required_cdns(client: httpx.AsyncClient) -> None:
    """The CSP allows the two CDNs Phase 6 still loads (Tailwind, Firebase) and
    no longer whitelists HTMX (removed in Phase 7)."""
    response = await client.get("/api/health")
    csp = response.headers["content-security-policy"]
    assert "https://cdn.tailwindcss.com" in csp
    assert "https://www.gstatic.com" in csp
    assert "https://unpkg.com" not in csp


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


_REQUIRED_SECURITY_HEADERS = (
    "content-security-policy",
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
)


@pytest.fixture()
async def status_client() -> AsyncIterator[httpx.AsyncClient]:
    """A FastAPI app with security middleware + routes producing 200/401/404/422/500.

    Uses a synthetic sub-app rather than the production routers so the test
    can deterministically hit each status code without having to satisfy
    auth dependencies (or rely on path-vs-body validation order, which is
    implementation-defined in FastAPI).
    """
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    from app.core.security import configure_security_middleware

    app = FastAPI()
    configure_security_middleware(app)

    @app.get("/probe-ok")
    async def _probe_ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/probe-unauthorized")
    async def _probe_unauthorized() -> None:
        raise HTTPException(status_code=401, detail="unauthorized")

    class _Payload(BaseModel):
        value: int

    @app.post("/probe-needs-body")
    async def _probe_needs_body(payload: _Payload) -> _Payload:
        return payload

    @app.get("/probe-boom")
    async def _probe_boom() -> None:
        raise RuntimeError("synthetic test failure")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "expected_status", "kwargs"),
    [
        ("GET", "/probe-ok", 200, {}),
        ("GET", "/probe-unauthorized", 401, {}),
        ("GET", "/this-path-does-not-exist", 404, {}),
        ("POST", "/probe-needs-body", 422, {"json": {}}),
        ("GET", "/probe-boom", 500, {}),
    ],
    ids=["200", "401", "404", "422", "500"],
)
async def test_security_headers_emitted_on_every_status(
    status_client: httpx.AsyncClient,
    method: str,
    path: str,
    expected_status: int,
    kwargs: dict[str, Any],
) -> None:
    """Every response — including Starlette-synthesised 404/422 and the
    middleware-synthesised 500 — carries the full set of security headers."""
    response = await status_client.request(method, path, **kwargs)
    assert response.status_code == expected_status
    lowercase_keys = {key.lower() for key in response.headers}
    for required in _REQUIRED_SECURITY_HEADERS:
        assert required in lowercase_keys, (
            f"{required!r} missing on status {expected_status} ({method} {path}); "
            f"got headers: {sorted(lowercase_keys)}"
        )
