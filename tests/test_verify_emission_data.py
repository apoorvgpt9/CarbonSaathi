"""Tests for scripts/verify_emission_data.py — check functions and subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_emission_data import (
    check_food_factors,
    check_grid_factors,
    check_transport_factors,
)

_DATA_DIR = Path(__file__).parent.parent / "app" / "data"
_SCRIPT = Path(__file__).parent.parent / "scripts" / "verify_emission_data.py"


# ── Pass against real data ────────────────────────────────────────────────────


def test_check_grid_factors_passes_real_data() -> None:
    check_grid_factors(_DATA_DIR / "state_grid_factors.json")


def test_check_transport_factors_passes_real_data() -> None:
    check_transport_factors(_DATA_DIR / "transport_factors.json")


def test_check_food_factors_passes_real_data() -> None:
    check_food_factors(_DATA_DIR / "food_factors.json")


# ── Fail on corrupted fixtures ────────────────────────────────────────────────


def test_check_grid_factors_fails_bad_entry(tmp_path: Path) -> None:
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
                        "source": "fake source long enough to pass length check here",
                        "confidence": "medium",
                        "last_verified": "2024-01-01",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="Delhi"):
        check_grid_factors(bad)


def test_check_grid_factors_fails_missing_state(tmp_path: Path) -> None:
    """A grid file that covers only a subset of states must fail."""
    bad = tmp_path / "state_grid_factors.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "unit": "kg_co2e_per_kwh",
                "entries": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="missing"):
        check_grid_factors(bad)


def test_check_grid_factors_fails_schema_version_missing(tmp_path: Path) -> None:
    bad = tmp_path / "state_grid_factors.json"
    bad.write_text(
        json.dumps({"unit": "kg_co2e_per_kwh", "entries": {}}),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="schema_version"):
        check_grid_factors(bad)


def test_check_grid_factors_fails_wrong_unit(tmp_path: Path) -> None:
    bad = tmp_path / "state_grid_factors.json"
    bad.write_text(
        json.dumps({"schema_version": "1", "unit": "wrong_unit", "entries": {}}),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="unit"):
        check_grid_factors(bad)


def test_check_transport_factors_fails_missing_key(tmp_path: Path) -> None:
    bad = tmp_path / "transport_factors.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "unit": "kg_co2e_per_km",
                "entries": {
                    "metro": {
                        "value": 0.031,
                        "unit": "kg_co2e_per_km",
                        "source": "DMRC Sustainability Report 2022-23 (per passenger-km)",
                        "confidence": "medium",
                        "last_verified": "2023-06-01",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="missing"):
        check_transport_factors(bad)


def test_check_food_factors_fails_estimated_without_notes(tmp_path: Path) -> None:
    """An estimated entry with null notes must fail the check."""
    real_path = _DATA_DIR / "food_factors.json"
    real: dict[str, object] = json.loads(real_path.read_text(encoding="utf-8"))
    entries = real["entries"]
    assert isinstance(entries, dict)
    # Force veg_meal to estimated with no notes
    veg = dict(entries["veg_meal"])
    veg["confidence"] = "estimated"
    veg["notes"] = None
    entries["veg_meal"] = veg

    bad = tmp_path / "food_factors.json"
    bad.write_text(json.dumps(real), encoding="utf-8")

    with pytest.raises(AssertionError, match="estimated"):
        check_food_factors(bad)


def test_check_food_factors_fails_short_source(tmp_path: Path) -> None:
    """An entry with a source shorter than 10 chars must fail."""
    real_path = _DATA_DIR / "food_factors.json"
    real: dict[str, object] = json.loads(real_path.read_text(encoding="utf-8"))
    entries = real["entries"]
    assert isinstance(entries, dict)
    egg = dict(entries["egg_single"])
    egg["source"] = "short"
    entries["egg_single"] = egg

    bad = tmp_path / "food_factors.json"
    bad.write_text(json.dumps(real), encoding="utf-8")

    with pytest.raises(AssertionError, match="source"):
        check_food_factors(bad)


# ── End-to-end subprocess ─────────────────────────────────────────────────────


def test_script_exits_0_on_real_data() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=_SCRIPT.parent.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "OK: state_grid_factors.json" in result.stdout
    assert "OK: transport_factors.json" in result.stdout
    assert "OK: food_factors.json" in result.stdout
