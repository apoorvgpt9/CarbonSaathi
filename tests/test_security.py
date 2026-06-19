"""Tests for security-headers middleware."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_security_headers_present() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/health")

    headers = {key.lower(): value for key, value in response.headers.items()}
    assert headers["x-content-type-options"] == "nosniff"
    assert "x-frame-options" in headers
    assert "referrer-policy" in headers
