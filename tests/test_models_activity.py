"""Tests for app/models/activity.py — Activity, ActivityType, Confidence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.activity import (
    Activity,
    ElectricityData,
    FoodData,
    TransportData,
)
from app.models.shared import AgentReasoning


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _valid_reasoning() -> AgentReasoning:
    return AgentReasoning(
        agent_name="logger",
        prompt_version="1.0.0",
        input_summary="Took an Uber 12 km",
        reasoning_steps=["Identified transport mode: cab", "Applied ICCT factor"],
        output_summary="0.3120 kg CO2e",
        model="gemini-2.5-flash",
        latency_ms=410,
    )


def _valid_activity(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "act-001",
        "user_id": "user-123",
        "type": "transport",
        "timestamp": _utc_now(),
        "raw_input": "Took Uber from home to office, around 12 km",
        "structured_data": {"mode": "cab", "distance_km": 12},
        "emission_kg_co2e": 0.3120,
        "confidence": "high",
        "emission_factor_source": "ICCT 2022",
    }
    base.update(overrides)
    return base


def test_activity_valid() -> None:
    a = Activity(**_valid_activity())
    assert a.id == "act-001"
    assert a.emission_kg_co2e == pytest.approx(0.3120)
    assert a.agent_reasoning is None


def test_activity_negative_emission_rejected() -> None:
    with pytest.raises(ValidationError):
        Activity(**_valid_activity(emission_kg_co2e=-0.01))


def test_activity_raw_input_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        Activity(**_valid_activity(raw_input=""))


def test_activity_raw_input_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        Activity(**_valid_activity(raw_input="x" * 501))


def test_activity_raw_input_max_length_ok() -> None:
    a = Activity(**_valid_activity(raw_input="x" * 500))
    assert len(a.raw_input) == 500


def test_activity_invalid_type_rejected() -> None:
    with pytest.raises(ValidationError):
        Activity(**_valid_activity(type="shopping"))


def test_activity_invalid_confidence_rejected() -> None:
    with pytest.raises(ValidationError):
        Activity(**_valid_activity(confidence="certain"))


def test_activity_optional_agent_reasoning_absent() -> None:
    a = Activity(**_valid_activity())
    assert a.agent_reasoning is None


def test_activity_optional_agent_reasoning_present() -> None:
    a = Activity(**_valid_activity(agent_reasoning=_valid_reasoning()))
    assert a.agent_reasoning is not None
    assert a.agent_reasoning.agent_name == "logger"


def test_activity_emission_factor_source_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        Activity(**_valid_activity(emission_factor_source=""))


def test_activity_is_frozen() -> None:
    a = Activity(**_valid_activity())
    with pytest.raises((AttributeError, ValidationError)):
        a.emission_kg_co2e = 99.0  # type: ignore[misc]


def test_transport_data_valid() -> None:
    data = TransportData(mode="taxi_petrol", km=12.0)
    assert data.mode == "taxi_petrol"
    assert data.km == pytest.approx(12.0)
    assert data.notes is None


def test_transport_data_empty_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        TransportData(mode="", km=1.0)


def test_transport_data_negative_km_rejected() -> None:
    with pytest.raises(ValidationError):
        TransportData(mode="metro", km=-1.0)


def test_transport_data_km_too_large_rejected() -> None:
    with pytest.raises(ValidationError):
        TransportData(mode="metro", km=10001.0)


def test_electricity_data_kwh_only_valid() -> None:
    data = ElectricityData(kwh=90.0)
    assert data.kwh == pytest.approx(90.0)
    assert data.bill_amount_inr is None


def test_electricity_data_bill_only_valid() -> None:
    data = ElectricityData(bill_amount_inr=800.0)
    assert data.bill_amount_inr == pytest.approx(800.0)
    assert data.kwh is None


def test_electricity_data_requires_kwh_or_bill() -> None:
    with pytest.raises(ValidationError):
        ElectricityData(appliance="AC", hours=3.0)


def test_electricity_data_negative_kwh_rejected() -> None:
    with pytest.raises(ValidationError):
        ElectricityData(kwh=-1.0)


def test_food_data_valid() -> None:
    data = FoodData(category="veg_meal", servings=2.0)
    assert data.category == "veg_meal"
    assert data.servings == pytest.approx(2.0)


def test_food_data_zero_servings_rejected() -> None:
    with pytest.raises(ValidationError):
        FoodData(category="veg_meal", servings=0)


def test_food_data_too_many_servings_rejected() -> None:
    with pytest.raises(ValidationError):
        FoodData(category="veg_meal", servings=21)


def test_food_data_empty_category_rejected() -> None:
    with pytest.raises(ValidationError):
        FoodData(category="", servings=1.0)
