"""Tests for the server-rendered HTML page routes (Phase 6).

Covers all six pages in :mod:`app.routes.pages`.  Each page is publicly
reachable (no auth dep) and renders an HTML response that includes the
Phase 6 CDN script tags plus the ``/static/js/auth.js`` module reference.
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


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/", "Sign in with Google"),
        ("/onboarding", "onboarding-form"),
        ("/dashboard", "today-kg"),
        ("/log", 'name="raw_input"'),
        ("/insights", 'data-action="stream-insights"'),
        ("/recommendations", 'id="recommendations-list"'),
    ],
)
async def test_page_returns_html(client: httpx.AsyncClient, path: str, marker: str) -> None:
    """Every page returns 200 + text/html and contains its page-specific marker."""
    resp = await client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert marker in resp.text


@pytest.mark.parametrize(
    "path",
    ["/", "/onboarding", "/dashboard", "/log", "/insights", "/recommendations"],
)
async def test_page_loads_required_cdns_and_app_js(client: httpx.AsyncClient, path: str) -> None:
    """Every page references Tailwind CDN, HTMX CDN, and /static/js/auth.js."""
    resp = await client.get(path)
    body = resp.text
    assert "cdn.tailwindcss.com" in body
    assert "unpkg.com/htmx.org" in body
    assert "/static/js/auth.js" in body


async def test_onboarding_renders_all_states(client: httpx.AsyncClient) -> None:
    """The onboarding select renders every IndianState value (28 states + 8 UTs)."""
    from app.models.user import IndianState

    resp = await client.get("/onboarding")
    body = resp.text
    for state in IndianState:
        assert state.value in body


async def test_static_css_reachable(client: httpx.AsyncClient) -> None:
    """The /static mount serves app.css."""
    resp = await client.get("/static/css/app.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]


async def test_static_auth_js_reachable(client: httpx.AsyncClient) -> None:
    """The /static mount serves auth.js."""
    resp = await client.get("/static/js/auth.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


async def test_static_sse_consumer_reachable(client: httpx.AsyncClient) -> None:
    """The /static mount serves the SSE consumer module."""
    resp = await client.get("/static/js/sse_consumer.js")
    assert resp.status_code == 200


async def test_pages_have_lang_attribute(client: httpx.AsyncClient) -> None:
    """The base template sets <html lang=\"en\">."""
    resp = await client.get("/")
    assert '<html lang="en">' in resp.text


async def test_pages_have_skip_link(client: httpx.AsyncClient) -> None:
    """The base template includes the skip-to-main accessibility link."""
    resp = await client.get("/")
    assert 'href="#main"' in resp.text
