"""Tests for app/models/emission.py — FactorEntry, FactorLookupResult, Confidence."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.models.emission import FactorEntry, FactorLookupResult
from app.models.shared import Confidence

# ── Helpers ───────────────────────────────────────────────────────────────────


def _valid_entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "value": 0.82,
        "unit": "kg_co2e_per_kwh",
        "source": (
            "Central Electricity Authority (CEA), " "CO2 Baseline Database, Version 19.0 (2023-24)"
        ),
        "confidence": "medium",
        "last_verified": "2024-01-01",
    }
    base.update(overrides)
    return base


# ── FactorEntry — valid construction ─────────────────────────────────────────


def test_factor_entry_valid_all_fields() -> None:
    entry = FactorEntry(**_valid_entry(notes="Northern grid average"))
    assert entry.value == pytest.approx(0.82)
    assert entry.unit == "kg_co2e_per_kwh"
    assert entry.confidence == "medium"
    assert isinstance(entry.last_verified, date)
    assert entry.notes == "Northern grid average"


def test_factor_entry_valid_no_notes() -> None:
    entry = FactorEntry(**_valid_entry())
    assert entry.notes is None


def test_factor_entry_zero_value_allowed() -> None:
    entry = FactorEntry(**_valid_entry(value=0.0))
    assert entry.value == pytest.approx(0.0)


def test_factor_entry_confidence_all_valid_values() -> None:
    for conf in ("high", "medium", "estimated"):
        entry = FactorEntry(**_valid_entry(confidence=conf))
        assert entry.confidence == conf


# ── FactorEntry — validation failures ────────────────────────────────────────


def test_factor_entry_negative_value_rejected() -> None:
    with pytest.raises(ValidationError):
        FactorEntry(**_valid_entry(value=-0.001))


def test_factor_entry_empty_source_rejected() -> None:
    with pytest.raises(ValidationError):
        FactorEntry(**_valid_entry(source=""))


def test_factor_entry_empty_unit_rejected() -> None:
    with pytest.raises(ValidationError):
        FactorEntry(**_valid_entry(unit=""))


def test_factor_entry_missing_value_rejected() -> None:
    data = _valid_entry()
    del data["value"]
    with pytest.raises(ValidationError):
        FactorEntry(**data)


def test_factor_entry_missing_source_rejected() -> None:
    data = _valid_entry()
    del data["source"]
    with pytest.raises(ValidationError):
        FactorEntry(**data)


def test_factor_entry_missing_confidence_rejected() -> None:
    data = _valid_entry()
    del data["confidence"]
    with pytest.raises(ValidationError):
        FactorEntry(**data)


def test_factor_entry_invalid_confidence_rejected() -> None:
    with pytest.raises(ValidationError):
        FactorEntry(**_valid_entry(confidence="unknown"))


def test_factor_entry_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        FactorEntry(**_valid_entry(unexpected_field="should fail"))


def test_factor_entry_frozen_rejects_assignment() -> None:
    entry = FactorEntry(**_valid_entry())
    with pytest.raises(ValidationError):
        entry.value = 999.0  # type: ignore[misc]


# ── FactorLookupResult ────────────────────────────────────────────────────────


def test_factor_lookup_result_shape() -> None:
    entry = FactorEntry(**_valid_entry())
    result = FactorLookupResult(key="Delhi", entry=entry)
    assert result.key == "Delhi"
    assert result.entry is entry
    assert isinstance(result.entry, FactorEntry)


def test_factor_lookup_result_extra_field_rejected() -> None:
    entry = FactorEntry(**_valid_entry())
    with pytest.raises(ValidationError):
        FactorLookupResult(key="Delhi", entry=entry, extra_key="no")  # type: ignore[call-arg]


def test_factor_lookup_result_frozen_rejects_assignment() -> None:
    entry = FactorEntry(**_valid_entry())
    result = FactorLookupResult(key="Delhi", entry=entry)
    with pytest.raises(ValidationError):
        result.key = "Mumbai"  # type: ignore[misc]


# ── Confidence re-export backward-compat ──────────────────────────────────────


def test_confidence_still_importable_from_activity() -> None:
    """activity.py must still export Confidence for backward compatibility."""
    from app.models.activity import Confidence as ActivityConfidence

    assert ActivityConfidence == Confidence


def test_confidence_literal_has_expected_args() -> None:
    import typing

    args = typing.get_args(Confidence)
    assert set(args) == {"high", "medium", "estimated"}
