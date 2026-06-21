"""Golden activity fixture sets for Phase 8 agent tests.

Provides four typed ``list[Activity]`` fixture sets representing realistic
Indian metro professional (Riya/Rahul) carbon profiles.  All sets use a fixed
reference timestamp so tests are deterministic and independent of wall-clock time.

Fixture sets
------------
``HIGH_COMMUTE``
    Five transport-heavy activities — the user commutes daily by petrol taxi.
    Expected Analyst signal: transport dominates the footprint.

``HIGH_FOOD``
    Five food-heavy activities — the user has frequent non-vegetarian meals.
    Expected Analyst signal: food (especially mutton) drives emissions.

``BALANCED``
    Five mixed activities covering transport, electricity, and food in roughly
    equal proportion.
    Expected Analyst signal: no single category dominates.

``INSUFFICIENT_DATA``
    Two activities — deliberately below :data:`MIN_ACTIVITIES_FOR_INSIGHTS`
    (= 3), so the Analyst must return :class:`~app.agents.analyst_agent.AnalystEmpty`
    without calling Gemini.

Design notes
------------
* Activities are constructed via the Pydantic model constructor, so they go
  through the same validation path as production code.
* Emission values are pre-computed from the real emission factors in
  ``app/data/`` (transport: kg_co2e_per_km, food: kg_co2e_per_serving).
* Timestamps are offsets from ``_FIXTURE_NOW``, spread across the current and
  last week to exercise the ``bucket_by_week`` bucketing logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.activity import Activity

_FIXTURE_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
"""Fixed reference timestamp used for all fixture activities."""

_UID = "golden-user-riya"
"""Canonical UID for fixture activities (Riya, Indian metro professional)."""

# ---------------------------------------------------------------------------
# Transport factors used (from app/data/transport_factors.json)
# taxi_petrol : 0.170 kg CO2e / km
# metro       : 0.031 kg CO2e / km
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# HIGH_COMMUTE — five activities, transport-heavy
# ---------------------------------------------------------------------------

HIGH_COMMUTE: list[Activity] = [
    # This week: four cab commutes (25 km each way = 4.25 kg CO2e each)
    Activity(
        id="hc-a1",
        user_id=_UID,
        type="transport",
        timestamp=_FIXTURE_NOW - timedelta(days=1),
        raw_input="Took Ola cab to office, about 25 km",
        structured_data={"mode": "taxi_petrol", "km": 25.0},
        emission_kg_co2e=round(0.170 * 25.0, 4),  # 4.25
        confidence="high",
        emission_factor_source="ICCT India 2023",
        agent_reasoning=None,
    ),
    Activity(
        id="hc-a2",
        user_id=_UID,
        type="transport",
        timestamp=_FIXTURE_NOW - timedelta(days=2),
        raw_input="Cab back home from office, 25 km",
        structured_data={"mode": "taxi_petrol", "km": 25.0},
        emission_kg_co2e=round(0.170 * 25.0, 4),  # 4.25
        confidence="high",
        emission_factor_source="ICCT India 2023",
        agent_reasoning=None,
    ),
    Activity(
        id="hc-a3",
        user_id=_UID,
        type="transport",
        timestamp=_FIXTURE_NOW - timedelta(days=3),
        raw_input="Uber to client site, 20 km",
        structured_data={"mode": "taxi_petrol", "km": 20.0},
        emission_kg_co2e=round(0.170 * 20.0, 4),  # 3.4
        confidence="high",
        emission_factor_source="ICCT India 2023",
        agent_reasoning=None,
    ),
    # Last week: two more taxi trips
    Activity(
        id="hc-a4",
        user_id=_UID,
        type="transport",
        timestamp=_FIXTURE_NOW - timedelta(days=8),
        raw_input="Cab to airport, 30 km",
        structured_data={"mode": "taxi_petrol", "km": 30.0},
        emission_kg_co2e=round(0.170 * 30.0, 4),  # 5.1
        confidence="high",
        emission_factor_source="ICCT India 2023",
        agent_reasoning=None,
    ),
    Activity(
        id="hc-a5",
        user_id=_UID,
        type="transport",
        timestamp=_FIXTURE_NOW - timedelta(days=9),
        raw_input="Taxi from railway station, 15 km",
        structured_data={"mode": "taxi_petrol", "km": 15.0},
        emission_kg_co2e=round(0.170 * 15.0, 4),  # 2.55
        confidence="high",
        emission_factor_source="ICCT India 2023",
        agent_reasoning=None,
    ),
]

# ---------------------------------------------------------------------------
# HIGH_FOOD — five activities, food-heavy
# ---------------------------------------------------------------------------
# non_veg_meal_mutton   : 4.50 kg CO2e / serving
# non_veg_meal_chicken  : 2.10 kg CO2e / serving

HIGH_FOOD: list[Activity] = [
    Activity(
        id="hf-a1",
        user_id=_UID,
        type="food",
        timestamp=_FIXTURE_NOW - timedelta(days=1),
        raw_input="Mutton biryani for lunch",
        structured_data={"category": "non_veg_meal_mutton", "servings": 1.0},
        emission_kg_co2e=4.50,
        confidence="estimated",
        emission_factor_source="FAO 2022",
        agent_reasoning=None,
    ),
    Activity(
        id="hf-a2",
        user_id=_UID,
        type="food",
        timestamp=_FIXTURE_NOW - timedelta(days=2),
        raw_input="Chicken curry with rice for dinner",
        structured_data={"category": "non_veg_meal_chicken", "servings": 1.0},
        emission_kg_co2e=2.10,
        confidence="estimated",
        emission_factor_source="FAO 2022",
        agent_reasoning=None,
    ),
    Activity(
        id="hf-a3",
        user_id=_UID,
        type="food",
        timestamp=_FIXTURE_NOW - timedelta(days=3),
        raw_input="Mutton rogan josh at restaurant",
        structured_data={"category": "non_veg_meal_mutton", "servings": 1.0},
        emission_kg_co2e=4.50,
        confidence="estimated",
        emission_factor_source="FAO 2022",
        agent_reasoning=None,
    ),
    Activity(
        id="hf-a4",
        user_id=_UID,
        type="food",
        timestamp=_FIXTURE_NOW - timedelta(days=8),
        raw_input="Chicken tikka masala lunch",
        structured_data={"category": "non_veg_meal_chicken", "servings": 1.0},
        emission_kg_co2e=2.10,
        confidence="estimated",
        emission_factor_source="FAO 2022",
        agent_reasoning=None,
    ),
    Activity(
        id="hf-a5",
        user_id=_UID,
        type="food",
        timestamp=_FIXTURE_NOW - timedelta(days=10),
        raw_input="Mutton seekh kebab snack",
        structured_data={"category": "non_veg_meal_mutton", "servings": 1.0},
        emission_kg_co2e=4.50,
        confidence="estimated",
        emission_factor_source="FAO 2022",
        agent_reasoning=None,
    ),
]

# ---------------------------------------------------------------------------
# BALANCED — five activities, mixed (transport + electricity + food)
# ---------------------------------------------------------------------------

BALANCED: list[Activity] = [
    Activity(
        id="bal-a1",
        user_id=_UID,
        type="transport",
        timestamp=_FIXTURE_NOW - timedelta(days=1),
        raw_input="Metro to office and back, about 12 km total",
        structured_data={"mode": "metro", "km": 12.0},
        emission_kg_co2e=round(0.031 * 12.0, 4),  # 0.372
        confidence="medium",
        emission_factor_source="DMRC 2022-23",
        agent_reasoning=None,
    ),
    Activity(
        id="bal-a2",
        user_id=_UID,
        type="electricity",
        timestamp=_FIXTURE_NOW - timedelta(days=2),
        raw_input="AC ran for about 4 hours, roughly 3 units consumed",
        structured_data={"kwh": 3.0},
        emission_kg_co2e=round(0.79 * 3.0, 4),  # Maharashtra grid ~0.79
        confidence="estimated",
        emission_factor_source="CEA 2023",
        agent_reasoning=None,
    ),
    Activity(
        id="bal-a3",
        user_id=_UID,
        type="food",
        timestamp=_FIXTURE_NOW - timedelta(days=3),
        raw_input="Chicken curry for lunch",
        structured_data={"category": "non_veg_meal_chicken", "servings": 1.0},
        emission_kg_co2e=2.10,
        confidence="estimated",
        emission_factor_source="FAO 2022",
        agent_reasoning=None,
    ),
    Activity(
        id="bal-a4",
        user_id=_UID,
        type="transport",
        timestamp=_FIXTURE_NOW - timedelta(days=8),
        raw_input="Cab to the market, about 5 km",
        structured_data={"mode": "taxi_petrol", "km": 5.0},
        emission_kg_co2e=round(0.170 * 5.0, 4),  # 0.85
        confidence="high",
        emission_factor_source="ICCT India 2023",
        agent_reasoning=None,
    ),
    Activity(
        id="bal-a5",
        user_id=_UID,
        type="food",
        timestamp=_FIXTURE_NOW - timedelta(days=9),
        raw_input="Veg thali dinner",
        structured_data={"category": "veg_meal", "servings": 1.0},
        emission_kg_co2e=0.90,
        confidence="estimated",
        emission_factor_source="FAO 2022",
        agent_reasoning=None,
    ),
]

# ---------------------------------------------------------------------------
# INSUFFICIENT_DATA — two activities (below MIN_ACTIVITIES_FOR_INSIGHTS = 3)
# ---------------------------------------------------------------------------

INSUFFICIENT_DATA: list[Activity] = [
    Activity(
        id="ins-a1",
        user_id=_UID,
        type="transport",
        timestamp=_FIXTURE_NOW - timedelta(days=1),
        raw_input="Short auto ride to the grocery store, 2 km",
        structured_data={"mode": "auto_rickshaw_cng", "km": 2.0},
        emission_kg_co2e=round(0.066 * 2.0, 4),  # 0.132
        confidence="medium",
        emission_factor_source="ICCT India 2020",
        agent_reasoning=None,
    ),
    Activity(
        id="ins-a2",
        user_id=_UID,
        type="food",
        timestamp=_FIXTURE_NOW - timedelta(days=2),
        raw_input="Veg thali for lunch",
        structured_data={"category": "veg_meal", "servings": 1.0},
        emission_kg_co2e=0.90,
        confidence="estimated",
        emission_factor_source="FAO 2022",
        agent_reasoning=None,
    ),
]
