"""Golden-set regression tests for CoachAgent.

These tests exercise the coach's full pipeline — input validation, bucketing,
Gemini response parsing, saving-basis computation, and outcome construction —
using the realistic :mod:`tests.fixtures.golden_activities` fixture sets.
Gemini is mocked at the SDK boundary so no network access occurs.

The most important test in this module is
:func:`test_coach_adversarial_savings_never_trusts_model`, which implements
DECISIONS.md § 14's invariant: the Coach computes ``expected_saving_kg``
deterministically from ``EmissionService`` and must NEVER use a figure supplied
by the model.  Mocked Gemini response returns a plausible-but-wrong implied
saving; the assertion verifies that the persisted saving matches the
``_evaluate_basis`` computation, not the model's value.

Distinct from existing ``test_agents_coach.py``
------------------------------------------------
The existing golden suite drives every JSON fixture in
``tests/fixtures/agent_goldens/coach/``.  These tests focus on *input*
realism (typed Activity objects from production-path construction) and the
adversarial savings invariant, which is not covered elsewhere.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.agents.coach_agent import (
    CoachAgent,
    CoachEmpty,
    CoachSuccess,
    TransportSwapBasis,
    _evaluate_basis,
)
from app.models.insight import Insight
from app.models.user import HomeProfile, IndianState, UserProfile
from app.services.emission_service import get_emission_service
from tests.fixtures.golden_activities import (
    _FIXTURE_NOW,
    _UID,
    BALANCED,
    HIGH_COMMUTE,
    HIGH_FOOD,
)

_SERVICE = get_emission_service()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(state: IndianState = IndianState.MAHARASHTRA) -> UserProfile:
    """Build a fully-onboarded user profile for the given state.

    Args:
        state: The Indian state used for grid-factor lookups.

    Returns:
        A complete :class:`~app.models.user.UserProfile` with
        ``onboarding_complete=True``.
    """
    return UserProfile(
        uid=_UID,
        email="riya@example.com",
        display_name="Riya",
        state=state,
        home_profile=HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="non-veg"),
        created_at=_FIXTURE_NOW,
        last_active=_FIXTURE_NOW,
        onboarding_complete=True,
    )


def _insight(title: str = "Transport heavy", insight_type: str = "pattern") -> Insight:
    """Build a minimal :class:`~app.models.insight.Insight` for coach context.

    Args:
        title: Short heading for the insight.
        insight_type: Insight category (``"pattern"``, ``"trend"``, etc.).

    Returns:
        A well-formed :class:`~app.models.insight.Insight`.
    """
    return Insight(
        id=f"ins-{title}",
        user_id=_UID,
        generated_at=_FIXTURE_NOW,
        type=insight_type,
        title=title,
        description="Context insight for Coach.",
        supporting_activity_ids=[],
        agent_reasoning=None,
    )


def _pro_json_model(payload: dict[str, Any]) -> MagicMock:
    """Return a mocked Gemini Pro model responding with ``payload`` as JSON.

    Args:
        payload: The JSON-serialisable recommendation payload.

    Returns:
        A :class:`unittest.mock.MagicMock` mimicking Gemini Pro.
    """
    model = MagicMock()
    model.model_name = "models/gemini-2.5-pro"
    model.generate_content_async = AsyncMock(return_value=SimpleNamespace(text=json.dumps(payload)))
    return model


def _make_agent(model: MagicMock) -> CoachAgent:
    """Build a :class:`CoachAgent` backed by the given mock model.

    Args:
        model: A mocked Gemini Pro model.

    Returns:
        A :class:`CoachAgent` wired to the mock and the real emission service.
    """
    factory = MagicMock()
    factory.pro.return_value = model
    return CoachAgent(emission_service=_SERVICE, gemini_factory=factory)


# ---------------------------------------------------------------------------
# B3-1: HIGH_COMMUTE — transport swap recommended and saving computed
# ---------------------------------------------------------------------------


async def test_coach_high_commute_recommends_transport_swap() -> None:
    """Coach with a transport-heavy fixture must produce a transport swap recommendation.

    The mocked response proposes a ``taxi_petrol → metro`` swap.  The test
    asserts that the recommendation survives validation, the saving is computed
    by the emission service (not from the model), and the outcome shape is
    correct.
    """
    payload = {
        "recommendations": [
            {
                "type": "swap",
                "title": "Switch to metro for daily commute",
                "description": (
                    "Taking the metro instead of a petrol cab for your regular commutes "
                    "would significantly cut your transport footprint."
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
    profile = _profile()
    agent = _make_agent(_pro_json_model(payload))

    outcome = await agent.generate_recommendations(
        profile=profile,
        activities=HIGH_COMMUTE,
        insights=[_insight("Transport dominates")],
        user_id=_UID,
        now=_FIXTURE_NOW,
    )

    assert isinstance(outcome, CoachSuccess), f"Expected success, got {outcome.status}"
    assert len(outcome.recommendations) >= 1
    rec = outcome.recommendations[0]
    assert rec.type == "swap"
    assert rec.expected_saving_kg > 0


# ---------------------------------------------------------------------------
# B3-2: HIGH_FOOD — food swap recommended
# ---------------------------------------------------------------------------


async def test_coach_high_food_recommends_food_swap() -> None:
    """Coach with a food-heavy fixture must produce a food-swap recommendation.

    The mocked response proposes a ``non_veg_meal_mutton → veg_meal`` swap.
    The test validates outcome shape and that the saving is positive.
    """
    payload = {
        "recommendations": [
            {
                "type": "swap",
                "title": "Try veg on some days",
                "description": (
                    "Swapping two of your weekly mutton meals for a veg thali "
                    "would meaningfully reduce your food footprint."
                ),
                "difficulty": "easy",
                "saving_basis": {
                    "kind": "food_swap",
                    "from_category": "non_veg_meal_mutton",
                    "to_category": "veg_meal",
                    "weekly_meals": 2.0,
                },
            }
        ]
    }
    profile = _profile()
    agent = _make_agent(_pro_json_model(payload))

    outcome = await agent.generate_recommendations(
        profile=profile,
        activities=HIGH_FOOD,
        insights=[_insight("Non-veg meals dominate", "pattern")],
        user_id=_UID,
        now=_FIXTURE_NOW,
    )

    assert isinstance(outcome, CoachSuccess), f"Expected success, got {outcome.status}"
    rec = outcome.recommendations[0]
    assert rec.type == "swap"
    # Computed saving: (4.50 - 0.90) * 2.0 = 7.2 kg/wk
    expected_saving = round((4.50 - 0.90) * 2.0, 4)
    assert (
        abs(rec.expected_saving_kg - expected_saving) < 1e-4
    ), f"Saving should be {expected_saving} kg; got {rec.expected_saving_kg}"


# ---------------------------------------------------------------------------
# B3-3: BALANCED — mixed profile succeeds
# ---------------------------------------------------------------------------


async def test_coach_balanced_profile_succeeds() -> None:
    """Coach with a balanced fixture must produce at least one recommendation.

    Validates that a mixed-category input does not confuse the prompt-building
    or validation logic, and that at least one recommendation survives.
    """
    payload = {
        "recommendations": [
            {
                "type": "reduce",
                "title": "Cut AC usage by one hour nightly",
                "description": (
                    "Running the AC one hour less each night " "reduces your electricity footprint."
                ),
                "difficulty": "easy",
                "saving_basis": {
                    "kind": "electricity_reduce",
                    "weekly_kwh_reduction": 5.0,
                },
            }
        ]
    }
    profile = _profile()
    agent = _make_agent(_pro_json_model(payload))

    outcome = await agent.generate_recommendations(
        profile=profile,
        activities=BALANCED,
        insights=[_insight("Mixed profile", "milestone")],
        user_id=_UID,
        now=_FIXTURE_NOW,
    )

    assert isinstance(outcome, CoachSuccess), f"Expected success, got {outcome.status}"
    assert len(outcome.recommendations) >= 1
    for rec in outcome.recommendations:
        assert rec.agent_reasoning is not None
        assert rec.agent_reasoning.agent_name == "coach"


# ---------------------------------------------------------------------------
# B3-4: Incomplete onboarding — CoachEmpty, no Gemini call
# ---------------------------------------------------------------------------


async def test_coach_incomplete_onboarding_returns_empty_without_gemini_call() -> None:
    """Coach returns ``CoachEmpty`` when the user has not completed onboarding.

    A user profile with ``state=None`` or ``home_profile=None`` cannot receive
    personalised recommendations.  The Coach must return ``CoachEmpty`` before
    making any Gemini call.
    """
    incomplete_profile = UserProfile(
        uid=_UID,
        email="riya@example.com",
        display_name="Riya",
        state=None,
        home_profile=None,
        created_at=_FIXTURE_NOW,
        last_active=_FIXTURE_NOW,
        onboarding_complete=False,
    )

    model = MagicMock()
    model.model_name = "models/gemini-2.5-pro"
    model.generate_content_async = AsyncMock(
        side_effect=AssertionError("Gemini must NOT be called for incomplete onboarding")
    )
    factory = MagicMock()
    factory.pro.return_value = model
    agent = CoachAgent(emission_service=_SERVICE, gemini_factory=factory)

    outcome = await agent.generate_recommendations(
        profile=incomplete_profile,
        activities=HIGH_COMMUTE,
        insights=[],
        user_id=_UID,
        now=_FIXTURE_NOW,
    )

    assert isinstance(outcome, CoachEmpty), f"Expected CoachEmpty, got {type(outcome).__name__}"
    assert "onboarding" in outcome.reason.lower()


# ---------------------------------------------------------------------------
# B3-5 (adversarial): Coach always computes saving — never trusts the model
#
# This is the single most important correctness invariant in the agent layer
# (DECISIONS.md § 14).  The mocked Gemini response deliberately implies a
# plausible-but-wrong saving_basis so we can verify that the agent derives
# expected_saving_kg from EmissionService, not from any model output.
# ---------------------------------------------------------------------------


async def test_coach_adversarial_savings_never_trusts_model() -> None:
    """Coach must derive ``expected_saving_kg`` from EmissionService, not the model.

    The mocked Gemini response proposes a ``taxi_petrol → metro`` swap over
    60 km/week.  We then verify that ``expected_saving_kg`` exactly matches
    what ``_evaluate_basis`` would compute from the real emission factors —
    regardless of any saving figure the model might have implied.

    The deterministic expectation (computed at import time from live factors)::

        saving = (taxi_petrol_factor - metro_factor) * weekly_km
               = (0.170 - 0.031) * 60.0
               = 0.139 * 60.0
               = 8.34 kg CO2e / week

    If the model were trusted and returned a different figure (e.g. 5.0 or
    10.0 kg), this test would fail — which is the intended behaviour.
    """
    # The basis the model proposes.
    basis = TransportSwapBasis(
        kind="transport_swap", from_mode="taxi_petrol", to_mode="metro", weekly_km=60.0
    )
    # What the emission service actually computes (ground truth).
    deterministic_saving, _ = _evaluate_basis(
        basis, emission_service=_SERVICE, state=IndianState.MAHARASHTRA
    )
    assert deterministic_saving is not None, "Precondition: basis must yield a valid saving"

    # Mocked Gemini payload — note the saving_basis is valid but we do NOT
    # include an expected_saving_kg field; the agent computes it.  Any stray
    # expected_saving_kg in the raw model JSON must be ignored (extra="ignore"
    # on _RecDraft ensures this), so we also inject a dummy value to prove it.
    payload = {
        "recommendations": [
            {
                "type": "swap",
                "title": "Metro over cab",
                "description": "Switch to metro for your daily commute to cut transport emissions.",
                "difficulty": "easy",
                # This is what the model 'claims' — intentionally wrong.
                "expected_saving_kg": 999.0,
                "saving_basis": {
                    "kind": "transport_swap",
                    "from_mode": "taxi_petrol",
                    "to_mode": "metro",
                    "weekly_km": 60.0,
                },
            }
        ]
    }
    profile = _profile(IndianState.MAHARASHTRA)
    agent = _make_agent(_pro_json_model(payload))

    outcome = await agent.generate_recommendations(
        profile=profile,
        activities=HIGH_COMMUTE,
        insights=[_insight("Transport dominates")],
        user_id=_UID,
        now=_FIXTURE_NOW,
    )

    assert isinstance(outcome, CoachSuccess), f"Expected CoachSuccess, got {type(outcome).__name__}"
    assert len(outcome.recommendations) == 1
    rec = outcome.recommendations[0]

    assert abs(rec.expected_saving_kg - deterministic_saving) < 1e-6, (
        f"expected_saving_kg ({rec.expected_saving_kg}) does not match the "
        f"EmissionService-computed value ({deterministic_saving}).  "
        "The Coach appears to be trusting the model's saving figure — "
        "this violates DECISIONS.md § 14."
    )
    # Explicitly assert the model's injected value was NOT used.
    assert rec.expected_saving_kg != 999.0, (
        "Coach used the model's injected expected_saving_kg=999.0 — "
        "this is the exact invariant violation DECISIONS.md § 14 prohibits."
    )
