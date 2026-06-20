"""Tests for app/routes/insights.py — list + content-negotiated stream."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

import app.routes.insights as insights
from app.agents.factories import get_analyst_agent, get_coach_agent
from app.core.auth import verify_firebase_token
from app.models.insight import Insight
from app.models.shared import AgentReasoning
from app.models.user import HomeProfile, IndianState, UserProfile
from app.services.firestore_service import get_firestore_service
from app.services.orchestrator import Done, PhaseComplete, PhaseStart, ReasoningStep
from tests._sse import parse_sse

_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Builders / helpers
# ---------------------------------------------------------------------------


def _insight() -> Insight:
    return Insight(
        id="i1",
        user_id="user-123",
        generated_at=_NOW,
        type="pattern",
        title="Title",
        description="Description",
        supporting_activity_ids=[],
        agent_reasoning=AgentReasoning(
            agent_name="analyst",
            prompt_version="v1",
            input_summary="in",
            reasoning_steps=["s"],
            output_summary="out",
            model="gemini-2.5-pro",
            latency_ms=5,
        ),
    )


def _profile() -> UserProfile:
    return UserProfile(
        uid="user-123",
        email="test@example.com",
        display_name="Test",
        state=IndianState.MAHARASHTRA,
        home_profile=HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="veg"),
        created_at=_NOW,
        last_active=_NOW,
        onboarding_complete=True,
    )


def _fake_pipeline(events: list[Any]) -> Any:
    async def _gen(**_kwargs: object) -> AsyncIterator[object]:
        for event in events:
            yield event

    return _gen


def _success_events() -> list[Any]:
    return [
        PhaseStart(phase="analyst"),
        ReasoningStep(phase="analyst", step="a1"),
        PhaseComplete(phase="analyst", status="success"),
        PhaseStart(phase="coach"),
        PhaseComplete(phase="coach", status="success"),
        Done(insights=[], recommendations=[], analyst_status="success", coach_status="success"),
    ]


async def _read_stream(client: httpx.AsyncClient, headers: dict[str, str]) -> tuple[int, str, str]:
    body = ""
    async with client.stream("GET", "/api/insights/stream", headers=headers) as resp:
        status = resp.status_code
        content_type = resp.headers.get("content-type", "")
        async for chunk in resp.aiter_text():
            body += chunk
    return status, content_type, body


@pytest.fixture
async def client_no_auth_insights(
    firestore_service_mock: AsyncMock,
) -> AsyncIterator[httpx.AsyncClient]:
    """Client with Firestore mocked but auth overridden to raise 401."""
    from fastapi import HTTPException

    from app.main import create_app

    app = create_app()

    def _raise_401() -> None:
        raise HTTPException(status_code=401, detail="Authentication failed")

    app.dependency_overrides[verify_firebase_token] = _raise_401
    app.dependency_overrides[get_firestore_service] = lambda: firestore_service_mock
    app.dependency_overrides[get_analyst_agent] = lambda: AsyncMock()
    app.dependency_overrides[get_coach_agent] = lambda: AsyncMock()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/insights (read-only)
# ---------------------------------------------------------------------------


async def test_list_insights_returns_cached(
    client_with_user: httpx.AsyncClient, firestore_service_mock: AsyncMock
) -> None:
    firestore_service_mock.get_recent_insights.return_value = [_insight()]

    resp = await client_with_user.get("/api/insights")

    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


async def test_list_insights_empty_is_200(
    client_with_user: httpx.AsyncClient, firestore_service_mock: AsyncMock
) -> None:
    firestore_service_mock.get_recent_insights.return_value = []

    resp = await client_with_user.get("/api/insights")

    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_list_insights_requires_auth(client_no_auth_insights: httpx.AsyncClient) -> None:
    resp = await client_no_auth_insights.get("/api/insights")

    assert resp.status_code == 401
    assert int(resp.headers["content-length"]) == 34
    assert resp.json() == {"detail": "Authentication failed"}


# ---------------------------------------------------------------------------
# GET /api/insights/stream
# ---------------------------------------------------------------------------


async def test_stream_sse_emits_parseable_events(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firestore_service_mock.get_user.return_value = _profile()
    monkeypatch.setattr(insights, "SSE_INTER_EVENT_DELAY_S", 0)
    monkeypatch.setattr(insights, "run_insight_pipeline", _fake_pipeline(_success_events()))

    status, content_type, body = await _read_stream(
        client_with_user, {"accept": "text/event-stream"}
    )

    assert status == 200
    assert content_type.startswith("text/event-stream")
    parsed = parse_sse(body)
    assert [e.event for e in parsed] == [
        "phase_start",
        "reasoning",
        "phase_complete",
        "phase_start",
        "phase_complete",
        "done",
    ]
    assert parsed[-1].event == "done"


async def test_stream_json_returns_single_payload(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firestore_service_mock.get_user.return_value = _profile()
    monkeypatch.setattr(insights, "run_insight_pipeline", _fake_pipeline(_success_events()))

    resp = await client_with_user.get(
        "/api/insights/stream", headers={"accept": "application/json"}
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["event"] == "done"
    assert "data:" not in resp.text


async def test_stream_both_accept_prefers_sse(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firestore_service_mock.get_user.return_value = _profile()
    monkeypatch.setattr(insights, "SSE_INTER_EVENT_DELAY_S", 0)
    monkeypatch.setattr(insights, "run_insight_pipeline", _fake_pipeline(_success_events()))

    status, content_type, _body = await _read_stream(
        client_with_user, {"accept": "application/json, text/event-stream"}
    )

    assert status == 200
    assert content_type.startswith("text/event-stream")


async def test_stream_empty_accept_defaults_to_sse(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firestore_service_mock.get_user.return_value = _profile()
    monkeypatch.setattr(insights, "SSE_INTER_EVENT_DELAY_S", 0)
    monkeypatch.setattr(insights, "run_insight_pipeline", _fake_pipeline(_success_events()))

    status, content_type, _body = await _read_stream(client_with_user, {"accept": ""})

    assert status == 200
    assert content_type.startswith("text/event-stream")


async def test_stream_cached_path_has_no_reasoning(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firestore_service_mock.get_user.return_value = _profile()
    monkeypatch.setattr(insights, "SSE_INTER_EVENT_DELAY_S", 0)
    cached = [
        PhaseComplete(phase="analyst", status="cached"),
        PhaseComplete(phase="coach", status="cached"),
        Done(insights=[], recommendations=[], analyst_status="cached", coach_status="cached"),
    ]
    monkeypatch.setattr(insights, "run_insight_pipeline", _fake_pipeline(cached))

    status, _content_type, body = await _read_stream(
        client_with_user, {"accept": "text/event-stream"}
    )

    assert status == 200
    parsed = parse_sse(body)
    assert [e.event for e in parsed] == ["phase_complete", "phase_complete", "done"]
    assert all(e.data["status"] == "cached" for e in parsed[:2])


async def test_stream_profile_missing_is_500(
    client_with_user: httpx.AsyncClient, firestore_service_mock: AsyncMock
) -> None:
    firestore_service_mock.get_user.return_value = None

    resp = await client_with_user.get(
        "/api/insights/stream", headers={"accept": "application/json"}
    )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Server error"


async def test_stream_requires_auth(client_no_auth_insights: httpx.AsyncClient) -> None:
    resp = await client_no_auth_insights.get("/api/insights/stream")

    assert resp.status_code == 401
    assert int(resp.headers["content-length"]) == 34
    assert resp.json() == {"detail": "Authentication failed"}


async def test_stream_json_incomplete_pipeline_is_500(
    client_with_user: httpx.AsyncClient,
    firestore_service_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firestore_service_mock.get_user.return_value = _profile()
    # Contract violation: the pipeline never yields a terminal ``done`` event.
    no_done = [
        PhaseStart(phase="analyst"),
        PhaseComplete(phase="analyst", status="success"),
    ]
    monkeypatch.setattr(insights, "run_insight_pipeline", _fake_pipeline(no_done))

    resp = await client_with_user.get(
        "/api/insights/stream", headers={"accept": "application/json"}
    )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Pipeline did not complete"
