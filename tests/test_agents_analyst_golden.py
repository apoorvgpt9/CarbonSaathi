"""Golden-set regression tests for AnalystAgent.

These tests exercise the analyst's full pipeline — input validation, weekly
bucketing, Gemini response parsing, insight grounding, and outcome
construction — using the realistic :mod:`tests.fixtures.golden_activities`
fixture sets.  Gemini is mocked at the SDK boundary so no network access
occurs and results are fully deterministic.

Distinct from the existing ``test_agents_analyst.py`` golden suite (which
drives every JSON-fixture file in ``tests/fixtures/agent_goldens/analyst/``),
these tests focus on *input* realism: the Activity objects are constructed from
typed Pydantic models using the same production path as real user data, rather
than from raw JSON spec dicts.

What is being tested
---------------------
* ``HIGH_COMMUTE`` fixture → analyst produces at least one ``"pattern"`` or
  ``"trend"`` insight whose description references transport.
* ``HIGH_FOOD`` fixture → analyst produces at least one insight whose
  description references food.
* ``BALANCED`` fixture → analyst succeeds with at least one insight (validates
  that a mixed-category input does not crash the pipeline).
* ``INSUFFICIENT_DATA`` fixture → analyst returns ``AnalystEmpty`` and
  *never calls Gemini* (model is set to raise ``AssertionError`` if invoked).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.agents.analyst_agent import (
    MIN_ACTIVITIES_FOR_INSIGHTS,
    AnalystAgent,
    AnalystEmpty,
    AnalystSuccess,
)
from tests.fixtures.golden_activities import (
    _FIXTURE_NOW,
    _UID,
    BALANCED,
    HIGH_COMMUTE,
    HIGH_FOOD,
    INSUFFICIENT_DATA,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pro_json_model(payload: dict[str, Any]) -> MagicMock:
    """Return a mocked Gemini Pro model that responds with ``payload`` as JSON.

    Args:
        payload: The JSON-serialisable object to return as ``response.text``.

    Returns:
        A :class:`unittest.mock.MagicMock` mimicking a Gemini Pro model.
    """
    model = MagicMock()
    model.model_name = "models/gemini-2.5-pro"
    model.generate_content_async = AsyncMock(return_value=SimpleNamespace(text=json.dumps(payload)))
    return model


def _must_not_call_model() -> MagicMock:
    """Return a mocked model that raises ``AssertionError`` if called.

    Used to verify that the Analyst skips the Gemini call when there are
    insufficient activities (below ``MIN_ACTIVITIES_FOR_INSIGHTS``).

    Returns:
        A :class:`unittest.mock.MagicMock` that fails if
        ``generate_content_async`` is invoked.
    """
    model = MagicMock()
    model.model_name = "models/gemini-2.5-pro"
    model.generate_content_async = AsyncMock(
        side_effect=AssertionError("Gemini must NOT be called for insufficient data")
    )
    return model


def _make_agent(model: MagicMock) -> AnalystAgent:
    """Build an :class:`AnalystAgent` backed by the given mock model.

    Args:
        model: A mocked Gemini Pro model.

    Returns:
        An :class:`AnalystAgent` wired to the mock.
    """
    factory = MagicMock()
    factory.pro.return_value = model
    return AnalystAgent(gemini_factory=factory)


# ---------------------------------------------------------------------------
# B2-1: HIGH_COMMUTE — transport signal propagates through validation
# ---------------------------------------------------------------------------


async def test_analyst_high_commute_returns_transport_insight() -> None:
    """Analyst with a transport-heavy fixture must produce a transport insight.

    The mocked Gemini response contains a ``"pattern"`` insight referencing
    transport.  The test asserts that the insight survives grounding and
    schema validation, and that the ``AnalystSuccess`` outcome shape is correct.
    """
    payload = {
        "insights": [
            {
                "type": "pattern",
                "title": "Heavy cab dependency",
                "description": (
                    "You rely on petrol cabs for almost every journey — "
                    "transport dominates your weekly footprint."
                ),
                "supporting_activity_ids": ["hc-a1", "hc-a2"],
            },
            {
                "type": "trend",
                "title": "Consistent high commute emissions",
                "description": (
                    "Your transport emissions have stayed above 3 kg CO2e "
                    "per trip across both weeks."
                ),
                "supporting_activity_ids": ["hc-a4", "hc-a5"],
            },
        ]
    }
    agent = _make_agent(_pro_json_model(payload))

    outcome = await agent.generate_insights(activities=HIGH_COMMUTE, user_id=_UID, now=_FIXTURE_NOW)

    assert isinstance(outcome, AnalystSuccess), f"Expected success, got {outcome.status}"
    titles = [i.title for i in outcome.insights]
    descriptions = " ".join(i.description for i in outcome.insights).lower()
    assert any(
        "transport" in d.lower() or "cab" in d.lower() for d in [descriptions]
    ), f"Expected at least one transport-related insight description; got: {titles}"
    # All supporting IDs must be valid activity IDs from the fixture.
    valid_ids = {a.id for a in HIGH_COMMUTE}
    for insight in outcome.insights:
        assert set(insight.supporting_activity_ids) <= valid_ids, (
            f"Insight '{insight.title}' references unknown activity IDs: "
            f"{set(insight.supporting_activity_ids) - valid_ids}"
        )


# ---------------------------------------------------------------------------
# B2-2: HIGH_FOOD — food signal propagates through validation
# ---------------------------------------------------------------------------


async def test_analyst_high_food_returns_food_insight() -> None:
    """Analyst with a food-heavy fixture must produce a food-related insight.

    The mocked response contains a ``"trend"`` insight referencing non-vegetarian
    food.  The test asserts that the insight passes grounding and that the
    ``AnalystSuccess`` outcome is well-formed.
    """
    payload = {
        "insights": [
            {
                "type": "trend",
                "title": "Non-veg meals driving food emissions",
                "description": (
                    "Mutton and chicken meals account for most of "
                    "your food-category emissions this fortnight."
                ),
                "supporting_activity_ids": ["hf-a1", "hf-a3"],
            },
            {
                "type": "pattern",
                "title": "Frequent non-veg meals",
                "description": (
                    "You have logged five non-vegetarian meals across two "
                    "weeks with no vegetarian alternatives."
                ),
                "supporting_activity_ids": ["hf-a2", "hf-a4"],
            },
        ]
    }
    agent = _make_agent(_pro_json_model(payload))

    outcome = await agent.generate_insights(activities=HIGH_FOOD, user_id=_UID, now=_FIXTURE_NOW)

    assert isinstance(outcome, AnalystSuccess), f"Expected success, got {outcome.status}"
    descriptions = " ".join(i.description for i in outcome.insights).lower()
    assert any(
        word in descriptions for word in ("food", "meal", "mutton", "chicken", "non-veg")
    ), "Expected at least one food-related keyword in insight descriptions"
    valid_ids = {a.id for a in HIGH_FOOD}
    for insight in outcome.insights:
        assert set(insight.supporting_activity_ids) <= valid_ids


# ---------------------------------------------------------------------------
# B2-3: BALANCED — mixed input succeeds with at least one insight
# ---------------------------------------------------------------------------


async def test_analyst_balanced_succeeds_with_mixed_insight() -> None:
    """Analyst with balanced fixture must produce at least one valid insight.

    A mixed-category input covering transport, electricity, and food must not
    confuse the bucketing or grounding logic.  The test validates that at least
    one insight survives and the agent_reasoning trace is populated.
    """
    payload = {
        "insights": [
            {
                "type": "milestone",
                "title": "Balanced carbon profile",
                "description": (
                    "Your emissions are spread across transport, electricity, and food "
                    "— no single category dominates this fortnight."
                ),
                "supporting_activity_ids": [],
            }
        ]
    }
    agent = _make_agent(_pro_json_model(payload))

    outcome = await agent.generate_insights(activities=BALANCED, user_id=_UID, now=_FIXTURE_NOW)

    assert isinstance(outcome, AnalystSuccess), f"Expected success, got {outcome.status}"
    assert len(outcome.insights) >= 1
    for insight in outcome.insights:
        assert (
            insight.agent_reasoning is not None
        ), "Each insight must carry an agent_reasoning trace"
        assert insight.agent_reasoning.agent_name == "analyst"


# ---------------------------------------------------------------------------
# B2-4: INSUFFICIENT_DATA — AnalystEmpty returned, Gemini never called
# ---------------------------------------------------------------------------


async def test_analyst_insufficient_data_returns_empty_without_gemini_call() -> None:
    """Analyst with fewer than ``MIN_ACTIVITIES_FOR_INSIGHTS`` activities returns ``AnalystEmpty``.

    Critically, the Gemini model must NOT be called (the fixture model raises
    ``AssertionError`` if invoked).  This guards the early-exit branch that
    protects against useless model calls on sparse data, and validates the
    ``MIN_ACTIVITIES_FOR_INSIGHTS`` boundary exactly.
    """
    assert len(INSUFFICIENT_DATA) < MIN_ACTIVITIES_FOR_INSIGHTS, (
        f"Fixture must have fewer than {MIN_ACTIVITIES_FOR_INSIGHTS} activities; "
        f"got {len(INSUFFICIENT_DATA)}"
    )

    agent = _make_agent(_must_not_call_model())

    outcome = await agent.generate_insights(
        activities=INSUFFICIENT_DATA, user_id=_UID, now=_FIXTURE_NOW
    )

    assert isinstance(outcome, AnalystEmpty), f"Expected AnalystEmpty, got {type(outcome).__name__}"
    assert str(MIN_ACTIVITIES_FOR_INSIGHTS) in outcome.reason, (
        f"AnalystEmpty reason should mention the threshold ({MIN_ACTIVITIES_FOR_INSIGHTS}); "
        f"got: {outcome.reason!r}"
    )
    assert outcome.agent_reasoning is not None
    assert outcome.agent_reasoning.agent_name == "analyst"
