"""Tests for GET /api/auth/config (public Firebase web-app config)."""

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


async def test_returns_200(client: httpx.AsyncClient) -> None:
    """GET /api/auth/config returns 200 without authentication."""
    resp = await client.get("/api/auth/config")
    assert resp.status_code == 200


async def test_response_shape(client: httpx.AsyncClient) -> None:
    """The body contains the four Firebase web-config keys, all strings."""
    resp = await client.get("/api/auth/config")
    body = resp.json()
    assert set(body.keys()) == {"apiKey", "authDomain", "projectId", "appId"}
    for value in body.values():
        assert isinstance(value, str)
        assert value != ""


async def test_values_match_settings(client: httpx.AsyncClient) -> None:
    """The returned values match the test environment fixture values."""
    resp = await client.get("/api/auth/config")
    body = resp.json()
    assert body["apiKey"] == "test-fb-api-key"
    assert body["authDomain"] == "test.firebaseapp.com"
    assert body["projectId"] == "test-project"
    assert body["appId"] == "1:test:web:test"


async def test_endpoint_is_public_no_auth_required(client: httpx.AsyncClient) -> None:
    """No Authorization header is required."""
    resp = await client.get("/api/auth/config")
    assert resp.status_code == 200
    assert resp.status_code != 401


async def test_post_returns_405(client: httpx.AsyncClient) -> None:
    """POST is not allowed on /api/auth/config."""
    resp = await client.post("/api/auth/config")
    assert resp.status_code == 405


async def test_content_type_is_json(client: httpx.AsyncClient) -> None:
    """The response is JSON."""
    resp = await client.get("/api/auth/config")
    assert "application/json" in resp.headers["content-type"]
