"""Full route → agent → Firestore-mock integration tests.

These tests exercise the complete request path for three key routes with the
agent logic running *for real* — only the Gemini SDK boundary is mocked.
This is distinct from the existing route tests (which mock at the agent-factory
level) and from the existing integration chain test (which tests agents directly
without going through the HTTP layer).

Concretely:
- ``verify_firebase_token`` and ``get_firestore_service`` are overridden with
  stubs/mocks as usual.
- ``get_logger_agent`` / ``get_analyst_agent`` / ``get_coach_agent`` are
  overridden with lambdas returning *real* agent instances backed by a mocked
  Gemini ``GenerativeModelFactory``.
- Real agent logic runs: input validation, governance checks, weekly bucketing,
  JSON parsing, grounding, saving computation, reasoning-trace construction.

Routes covered
--------------
C1-1  ``POST /api/activities``
    Real LoggerAgent with mocked Gemini flash → 201 response + Firestore write.

C1-2  ``GET /api/insights/stream`` (Accept: application/json)
    Real AnalystAgent + CoachAgent with mocked Gemini pro → full pipeline runs,
    insights and recommendations are written via the Firestore mock, and the
    terminal ``done`` JSON payload is returned.

C1-3  ``POST /api/recommendations/{rec_id}/accept``
    No agent involved; validates the recommendation accept mutation flows
    correctly from route → Firestore mock without any agent-level stubbing.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import google.generativeai as genai
import httpx
import pytest

from app.agents.analyst_agent import AnalystAgent
from app.agents.coach_agent import CoachAgent
from app.agents.factories import get_analyst_agent, get_coach_agent, get_logger_agent
from app.agents.logger_agent import LoggerAgent
from app.core.auth import CurrentUser, verify_firebase_token
from app.models.activity import Activity
from app.models.recommendation import Recommendation
from app.models.shared import AgentReasoning
from app.models.user import HomeProfile, IndianState, UserProfile
from app.services.emission_service import get_emission_service
from app.services.firestore_service import FirestoreService, get_firestore_service

_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
_UID = "chain-user-001"

# ---------------------------------------------------------------------------
# Shared mock-model builders (mirror test_integration_agent_chain.py pattern)
# ---------------------------------------------------------------------------


def _flash_function_call_model(name: str, args: dict[str, Any]) -> MagicMock:
    """Return a mocked Gemini Flash model that emits a single function call.

    Args:
        name: Function call name (e.g. ``"log_transport"``).
        args: Keyword arguments for the function call.

    Returns:
        A :class:`~unittest.mock.MagicMock` whose ``generate_content_async``
        returns a response with one candidate containing the given function call.
    """
    function_call = genai.protos.FunctionCall(name=name, args=args)
    part = SimpleNamespace(function_call=function_call)
    content = SimpleNamespace(parts=[part])
    response = SimpleNamespace(candidates=[SimpleNamespace(content=content)])
    model = MagicMock()
    model.model_name = "models/gemini-2.5-flash"
    model.generate_content_async = AsyncMock(return_value=response)
    return model


def _pro_json_model(payload: dict[str, Any]) -> MagicMock:
    """Return a mocked Gemini Pro model that responds with ``payload`` as JSON.

    Args:
        payload: The JSON-serialisable payload to return as ``response.text``.

    Returns:
        A :class:`~unittest.mock.MagicMock` whose ``generate_content_async``
        returns a ``SimpleNamespace`` with ``text`` set to the JSON string.
    """
    model = MagicMock()
    model.model_name = "models/gemini-2.5-pro"
    model.generate_content_async = AsyncMock(return_value=SimpleNamespace(text=json.dumps(payload)))
    return model


def _factory_for(model: MagicMock) -> MagicMock:
    """Return a mocked ``GenerativeModelFactory`` that always returns ``model``.

    Args:
        model: The model to return for both ``.flash()`` and ``.pro()`` calls.

    Returns:
        A :class:`~unittest.mock.MagicMock` mimicking
        :class:`~app.core.gemini.GenerativeModelFactory`.
    """
    factory = MagicMock()
    factory.flash.return_value = model
    factory.pro.return_value = model
    return factory


# ---------------------------------------------------------------------------
# Shared activity helpers
# ---------------------------------------------------------------------------


def _activity(aid: str, days_ago: int = 1) -> Activity:
    """Build a transport activity for use as a Firestore mock return value.

    Args:
        aid: Activity ID.
        days_ago: How many days before ``_NOW`` the activity occurred.

    Returns:
        A fully-formed :class:`~app.models.activity.Activity`.
    """
    return Activity(
        id=aid,
        user_id=_UID,
        type="transport",
        timestamp=_NOW - timedelta(days=days_ago),
        raw_input="Took Uber to office, about 12 km",
        structured_data={"mode": "taxi_petrol", "km": 12.0},
        emission_kg_co2e=round(0.170 * 12.0, 4),
        confidence="high",
        emission_factor_source="ICCT India 2023",
        agent_reasoning=None,
    )


def _profile() -> UserProfile:
    """Return the canonical fully-onboarded user profile for chain tests.

    Returns:
        A :class:`~app.models.user.UserProfile` with state and home profile set.
    """
    return UserProfile(
        uid=_UID,
        email="chain@example.com",
        display_name="Chain User",
        state=IndianState.MAHARASHTRA,
        home_profile=HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="non-veg"),
        created_at=_NOW,
        last_active=_NOW,
        onboarding_complete=True,
    )


def _recommendation() -> Recommendation:
    """Build a minimal recommendation for mock Firestore return values.

    Returns:
        A well-formed :class:`~app.models.recommendation.Recommendation`.
    """
    return Recommendation(
        id="rec-chain-1",
        user_id=_UID,
        generated_at=_NOW,
        type="swap",
        title="Switch to metro",
        description="Take the metro instead of a cab for your office commute.",
        expected_saving_kg=8.34,
        difficulty="easy",
        accepted=False,
        agent_reasoning=AgentReasoning(
            agent_name="coach",
            prompt_version="1.0.0",
            input_summary="4 activities, 1 insight",
            reasoning_steps=["Computed saving from emission service."],
            output_summary="1 recommendation produced.",
            model="gemini-2.5-pro",
            latency_ms=200,
        ),
    )


# ---------------------------------------------------------------------------
# C1-1: POST /api/activities — real LoggerAgent, mocked Gemini flash
# ---------------------------------------------------------------------------


@pytest.fixture
async def client_real_logger(
    current_user: CurrentUser,
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncMock]]:
    """Client with real LoggerAgent (mocked Gemini flash) and mocked Firestore.

    ``get_logger_agent`` is overridden with a real :class:`LoggerAgent` backed
    by a mocked flash Gemini model.  Only :func:`~app.core.auth.verify_firebase_token`
    and :func:`~app.services.firestore_service.get_firestore_service` use stubs.

    Args:
        current_user: The canonical authenticated user fixture.

    Yields:
        A ``(AsyncClient, firestore_mock)`` pair.
    """
    from app.main import create_app

    flash_model = _flash_function_call_model("log_transport", {"mode": "taxi_petrol", "km": 12.0})
    real_logger = LoggerAgent(
        emission_service=get_emission_service(),
        gemini_factory=_factory_for(flash_model),
    )
    fs_mock: AsyncMock = AsyncMock(spec=FirestoreService)
    fs_mock.get_user.return_value = _profile()
    fs_mock.add_activity.return_value = "act-chain-001"

    app = create_app()
    app.dependency_overrides[verify_firebase_token] = lambda: current_user
    app.dependency_overrides[get_firestore_service] = lambda: fs_mock
    app.dependency_overrides[get_logger_agent] = lambda: real_logger
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c, fs_mock
    finally:
        app.dependency_overrides.clear()


async def test_post_activity_real_logger_returns_201_and_calls_firestore(
    client_real_logger: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    """Real LoggerAgent must parse the input and persist an activity via Firestore.

    The flash Gemini mock returns ``log_transport(mode=taxi_petrol, km=12.0)``.
    The LoggerAgent runs its actual emission computation, governance, and
    reasoning-trace logic.  The test asserts:

    * HTTP 201 is returned.
    * The response body contains a valid ``activity`` with ``emission_kg_co2e``
      derived from the emission service (not made up).
    * ``agent_reasoning`` is present and names the ``"logger"`` agent.
    * ``FirestoreService.add_activity`` was called once with the persisted activity.
    """
    client, fs_mock = client_real_logger

    resp = await client.post("/api/activities", json={"raw_input": "Took Uber to office, 12 km"})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    activity = body["activity"]
    assert activity["type"] == "transport"
    assert activity["user_id"] == "user-123"  # current_user uid from conftest
    # Emission should be non-zero (derived from real emission service)
    assert activity["emission_kg_co2e"] > 0.0
    # Reasoning trace must be present and name the correct agent
    reasoning = body["agent_reasoning"]
    assert reasoning is not None
    assert reasoning["agent_name"] == "logger"
    # Firestore write must have happened exactly once
    fs_mock.add_activity.assert_called_once()
    saved: Activity = fs_mock.add_activity.call_args[0][0]
    assert saved.type == "transport"
    assert saved.emission_kg_co2e == pytest.approx(round(0.170 * 12.0, 4))


# ---------------------------------------------------------------------------
# C1-2: GET /api/insights/stream — real Analyst + Coach, mocked Gemini pro
# ---------------------------------------------------------------------------


@pytest.fixture
async def client_real_agents(
    current_user: CurrentUser,
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncMock]]:
    """Client with real Analyst + Coach agents (mocked Gemini pro) and mocked Firestore.

    ``get_analyst_agent`` and ``get_coach_agent`` are overridden with real
    agent instances backed by separate pro-model mocks, each returning the
    fixture payloads below.  The Firestore mock is pre-configured with the
    minimal set of return values required for a full pipeline run.

    Args:
        current_user: The canonical authenticated user fixture.

    Yields:
        A ``(AsyncClient, firestore_mock)`` pair.
    """
    from app.main import create_app
    from app.routes import insights as insights_module

    # Analyst model — returns one grounded pattern insight.
    analyst_payload = {
        "insights": [
            {
                "type": "pattern",
                "title": "Daily cab commute",
                "description": "You rely on petrol cabs for most of your office journeys.",
                "supporting_activity_ids": ["act-c1", "act-c2"],
            }
        ]
    }
    # Coach model — returns one transport-swap recommendation.
    coach_payload = {
        "recommendations": [
            {
                "type": "swap",
                "title": "Switch to metro",
                "description": (
                    "Taking the metro instead of a cab for your commute "
                    "cuts transport emissions."
                ),
                "difficulty": "easy",
                "saving_basis": {
                    "kind": "transport_swap",
                    "from_mode": "taxi_petrol",
                    "to_mode": "metro",
                    "weekly_km": 60.0,
                },
            }
        ]
    }

    real_analyst = AnalystAgent(gemini_factory=_factory_for(_pro_json_model(analyst_payload)))
    real_coach = CoachAgent(
        emission_service=get_emission_service(),
        gemini_factory=_factory_for(_pro_json_model(coach_payload)),
    )

    # Four activities — enough to clear MIN_ACTIVITIES_FOR_INSIGHTS = 3.
    activities = [
        _activity("act-c1", days_ago=1),
        _activity("act-c2", days_ago=2),
        _activity("act-c3", days_ago=3),
        _activity("act-c4", days_ago=9),
    ]

    fs_mock: AsyncMock = AsyncMock(spec=FirestoreService)
    fs_mock.get_user.return_value = _profile()
    fs_mock.get_generation_state.return_value = None  # pipeline is stale
    fs_mock.list_activities_in_range.return_value = activities
    fs_mock.add_insight.return_value = "ins-chain-1"
    fs_mock.add_recommendation.return_value = "rec-chain-1"
    fs_mock.set_generation_state.return_value = None

    app = create_app()
    app.dependency_overrides[verify_firebase_token] = lambda: current_user
    app.dependency_overrides[get_firestore_service] = lambda: fs_mock
    app.dependency_overrides[get_analyst_agent] = lambda: real_analyst
    app.dependency_overrides[get_coach_agent] = lambda: real_coach

    # Patch the inter-event SSE delay to 0 for test speed (not used for JSON
    # path, but patch anyway in case the SSE path is exercised in future).
    original_delay = insights_module.SSE_INTER_EVENT_DELAY_S
    insights_module.SSE_INTER_EVENT_DELAY_S = 0.0

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c, fs_mock
    finally:
        insights_module.SSE_INTER_EVENT_DELAY_S = original_delay
        app.dependency_overrides.clear()


async def test_insights_stream_real_agents_produces_insights_and_recs(
    client_real_agents: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    """Real agents must run full logic and write insights + recs via Firestore mock.

    The test uses ``Accept: application/json`` to receive a single ``done``
    payload (not SSE), which is simpler to assert.  The real AnalystAgent and
    CoachAgent execute their complete pipelines — bucketing, Gemini parsing,
    grounding, saving computation — with only the Gemini SDK calls mocked.

    Assertions:
    * HTTP 200 with a JSON body containing ``insights`` and ``recommendations``.
    * ``FirestoreService.add_insight`` called at least once.
    * ``FirestoreService.add_recommendation`` called at least once.
    * ``FirestoreService.set_generation_state`` called once at end of pipeline.
    * Each insight in the body carries an ``agent_reasoning`` with
      ``agent_name == "analyst"``.
    * Each recommendation carries ``expected_saving_kg > 0`` (computed by
      emission service, not the model).
    """
    client, fs_mock = client_real_agents

    resp = await client.get(
        "/api/insights/stream",
        headers={"Accept": "application/json"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "insights" in body
    assert "recommendations" in body

    # At least one insight must have survived the grounding + validation pipeline.
    assert len(body["insights"]) >= 1, "Expected at least one insight from real AnalystAgent"
    for ins in body["insights"]:
        assert ins["agent_reasoning"]["agent_name"] == "analyst"

    # At least one recommendation with a deterministic saving.
    assert (
        len(body["recommendations"]) >= 1
    ), "Expected at least one recommendation from real CoachAgent"
    for rec in body["recommendations"]:
        assert rec["expected_saving_kg"] > 0.0
        assert rec["agent_reasoning"]["agent_name"] == "coach"

    # Firestore writes must have been triggered.
    fs_mock.add_insight.assert_called()
    fs_mock.add_recommendation.assert_called()
    fs_mock.set_generation_state.assert_called_once()


# ---------------------------------------------------------------------------
# C1-3: POST /api/recommendations/{rec_id}/accept — route→Firestore chain
# ---------------------------------------------------------------------------


@pytest.fixture
async def client_recommendations_accept(
    current_user: CurrentUser,
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncMock]]:
    """Client with auth + Firestore mock for the recommendation accept route.

    No agents are involved in this route; the test validates that the HTTP
    route correctly delegates to ``FirestoreService.accept_recommendation`` and
    returns the expected response shape.

    Args:
        current_user: The canonical authenticated user fixture.

    Yields:
        A ``(AsyncClient, firestore_mock)`` pair.
    """
    from app.main import create_app

    fs_mock: AsyncMock = AsyncMock(spec=FirestoreService)

    app = create_app()
    app.dependency_overrides[verify_firebase_token] = lambda: current_user
    app.dependency_overrides[get_firestore_service] = lambda: fs_mock
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c, fs_mock
    finally:
        app.dependency_overrides.clear()


async def test_accept_recommendation_calls_firestore_and_returns_200(
    client_recommendations_accept: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    """Accepting a recommendation must call ``accept_recommendation`` and return 200.

    Validates the route → FirestoreService delegation chain: the service method
    is called with the correct ``user_id`` and ``rec_id``, and the response body
    has the expected ``accepted=True`` shape.
    """
    client, fs_mock = client_recommendations_accept
    fs_mock.accept_recommendation.return_value = True

    resp = await client.post("/api/recommendations/rec-abc-123/accept")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["rec_id"] == "rec-abc-123"
    fs_mock.accept_recommendation.assert_called_once_with("user-123", "rec-abc-123")


async def test_accept_recommendation_returns_404_when_not_found(
    client_recommendations_accept: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    """Accept must return 404 when ``accept_recommendation`` returns ``False``.

    Validates that the route correctly surfaces a not-found response without
    leaking ownership details.
    """
    client, fs_mock = client_recommendations_accept
    fs_mock.accept_recommendation.return_value = False

    resp = await client.post("/api/recommendations/rec-nonexistent/accept")

    assert resp.status_code == 404
