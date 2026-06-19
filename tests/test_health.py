"""Tests for the health-check endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import ValidationError

from app.routes.health import HealthResponse


@pytest.fixture()
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Provide an async ASGI test client for the full application."""
    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class TestHealthEndpoint:
    """Behavioural tests for GET /api/health."""

    async def test_returns_200(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_response_shape(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/health")
        assert response.json() == {"status": "ok", "version": "0.1.0"}

    async def test_content_type_is_json(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/health")
        assert "application/json" in response.headers["content-type"]

    async def test_security_headers_present(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/health")
        headers = {k.lower(): v for k, v in response.headers.items()}
        assert "x-frame-options" in headers
        assert "x-content-type-options" in headers
        assert "referrer-policy" in headers

    async def test_post_returns_405(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/health")
        assert response.status_code == 405

    async def test_unknown_route_returns_404(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/does-not-exist")
        assert response.status_code == 404


class TestHealthResponse:
    """Unit tests for the HealthResponse Pydantic model."""

    def test_valid_construction(self) -> None:
        resp = HealthResponse(status="ok", version="1.2.3")
        assert resp.status == "ok"
        assert resp.version == "1.2.3"

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthResponse(status="error", version="1.0.0")  # pydantic raises at runtime

    def test_version_is_string(self) -> None:
        resp = HealthResponse(status="ok", version="0.1.0")
        assert isinstance(resp.version, str)
