"""Tests for app/services/emission_service.py — EmissionService and singleton."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.emission import FactorLookupResult
from app.models.user import IndianState
from app.services.emission_service import (
    _DATA_DIR,
    EmissionDataError,
    EmissionService,
    get_emission_service,
)

# ── Construction ──────────────────────────────────────────────────────────────


def test_service_construction_succeeds() -> None:
    svc = EmissionService()
    assert svc is not None


# ── Grid factor lookups ───────────────────────────────────────────────────────


@pytest.mark.parametrize("state", list(IndianState))
def test_get_grid_factor_all_states(state: IndianState) -> None:
    svc = EmissionService()
    result = svc.get_grid_factor(state)
    assert isinstance(result, FactorLookupResult)
    assert result.key == state.value
    assert result.entry.value >= 0


def test_get_grid_factor_returns_correct_key() -> None:
    svc = EmissionService()
    result = svc.get_grid_factor(IndianState.DELHI)
    assert result.key == "Delhi"


# ── Transport factor lookups ──────────────────────────────────────────────────

_TRANSPORT_MODES = [
    "auto_rickshaw_cng",
    "bus_public",
    "four_wheeler_electric",
    "four_wheeler_petrol",
    "metro",
    "taxi_cng",
    "taxi_petrol",
    "two_wheeler_electric",
    "two_wheeler_petrol",
    "walking",
    "wfh",
]


@pytest.mark.parametrize("mode", _TRANSPORT_MODES)
def test_get_transport_factor_known_modes(mode: str) -> None:
    svc = EmissionService()
    result = svc.get_transport_factor(mode)
    assert isinstance(result, FactorLookupResult)
    assert result.key == mode
    assert result.entry.value >= 0


def test_get_transport_factor_unknown_returns_none() -> None:
    svc = EmissionService()
    assert svc.get_transport_factor("teleportation") is None


def test_get_transport_factor_walking_is_zero() -> None:
    svc = EmissionService()
    result = svc.get_transport_factor("walking")
    assert result is not None
    assert result.entry.value == pytest.approx(0.0)
    assert result.entry.confidence == "high"


def test_get_transport_factor_wfh_is_zero() -> None:
    svc = EmissionService()
    result = svc.get_transport_factor("wfh")
    assert result is not None
    assert result.entry.value == pytest.approx(0.0)


# ── Food factor lookups ───────────────────────────────────────────────────────

_FOOD_CATEGORIES = [
    "dal_serving",
    "dairy_serving_250ml",
    "egg_single",
    "non_veg_meal_chicken",
    "non_veg_meal_fish",
    "non_veg_meal_mutton",
    "paneer_serving_100g",
    "rice_serving",
    "snack_processed",
    "veg_meal",
]


@pytest.mark.parametrize("category", _FOOD_CATEGORIES)
def test_get_food_factor_known_categories(category: str) -> None:
    svc = EmissionService()
    result = svc.get_food_factor(category)
    assert isinstance(result, FactorLookupResult)
    assert result.key == category
    assert result.entry.value >= 0


def test_get_food_factor_unknown_returns_none() -> None:
    svc = EmissionService()
    assert svc.get_food_factor("unicorn_steak") is None


# ── List methods ──────────────────────────────────────────────────────────────


def test_list_transport_modes_count_and_sorted() -> None:
    svc = EmissionService()
    modes = svc.list_transport_modes()
    assert len(modes) == 11
    assert modes == sorted(modes)


def test_list_food_categories_count_and_sorted() -> None:
    svc = EmissionService()
    categories = svc.list_food_categories()
    assert len(categories) == 10
    assert categories == sorted(categories)


def test_list_transport_modes_contains_all_expected() -> None:
    svc = EmissionService()
    assert set(svc.list_transport_modes()) == set(_TRANSPORT_MODES)


def test_list_food_categories_contains_all_expected() -> None:
    svc = EmissionService()
    assert set(svc.list_food_categories()) == set(_FOOD_CATEGORIES)


# ── EmissionDataError on malformed files ──────────────────────────────────────


def _write_bad_grid(tmp_path: Path) -> Path:
    """Return path to a grid JSON with a negative-value entry."""
    bad = tmp_path / "state_grid_factors.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "unit": "kg_co2e_per_kwh",
                "entries": {
                    "Delhi": {
                        "value": -1.0,
                        "unit": "kg_co2e_per_kwh",
                        "source": "fake",
                        "confidence": "medium",
                        "last_verified": "2024-01-01",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return bad


def test_emission_data_error_on_bad_grid_json(tmp_path: Path) -> None:
    with pytest.raises(EmissionDataError, match="Delhi"):
        EmissionService(
            grid_path=_write_bad_grid(tmp_path),
            transport_path=_DATA_DIR / "transport_factors.json",
            food_path=_DATA_DIR / "food_factors.json",
        )


def test_emission_data_error_on_bad_transport_json(tmp_path: Path) -> None:
    bad = tmp_path / "transport_factors.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "unit": "kg_co2e_per_km",
                "entries": {
                    "metro": {
                        "value": -0.5,
                        "unit": "kg_co2e_per_km",
                        "source": "fake",
                        "confidence": "high",
                        "last_verified": "2023-01-01",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EmissionDataError, match="metro"):
        EmissionService(
            grid_path=_DATA_DIR / "state_grid_factors.json",
            transport_path=bad,
            food_path=_DATA_DIR / "food_factors.json",
        )


def test_emission_data_error_on_bad_food_json(tmp_path: Path) -> None:
    bad = tmp_path / "food_factors.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "unit": "kg_co2e_per_serving",
                "entries": {
                    "veg_meal": {
                        "value": -1.0,
                        "unit": "kg_co2e_per_serving",
                        "source": "fake",
                        "confidence": "estimated",
                        "last_verified": "2023-01-01",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EmissionDataError, match="veg_meal"):
        EmissionService(
            grid_path=_DATA_DIR / "state_grid_factors.json",
            transport_path=_DATA_DIR / "transport_factors.json",
            food_path=bad,
        )


def test_emission_data_error_on_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "state_grid_factors.json"
    bad.write_text("{ this is not valid json }", encoding="utf-8")
    with pytest.raises(EmissionDataError):
        EmissionService(
            grid_path=bad,
            transport_path=_DATA_DIR / "transport_factors.json",
            food_path=_DATA_DIR / "food_factors.json",
        )


# ── Singleton ─────────────────────────────────────────────────────────────────


def test_get_emission_service_singleton() -> None:
    get_emission_service.cache_clear()
    try:
        svc1 = get_emission_service()
        svc2 = get_emission_service()
        assert svc1 is svc2
    finally:
        get_emission_service.cache_clear()
