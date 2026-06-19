"""Verify emission factor JSON data files against schema and completeness rules.

Run standalone from the repository root::

    python3 scripts/verify_emission_data.py

Exit code 0 when all checks pass; exit code 1 on the first failure, with a
message written to ``stderr``.

The three check functions (:func:`check_grid_factors`,
:func:`check_transport_factors`, :func:`check_food_factors`) are importable
so the test suite can call them directly with custom fixture paths.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.models.emission import FactorEntry
from app.models.user import IndianState

_DATA_DIR: Path = Path(__file__).resolve().parent.parent / "app" / "data"

_EXPECTED_GRID_UNIT: str = "kg_co2e_per_kwh"
_EXPECTED_TRANSPORT_UNIT: str = "kg_co2e_per_km"
_EXPECTED_FOOD_UNIT: str = "kg_co2e_per_serving"

EXPECTED_TRANSPORT_MODES: frozenset[str] = frozenset(
    {
        "auto_rickshaw_cng",
        "metro",
        "bus_public",
        "taxi_petrol",
        "taxi_cng",
        "two_wheeler_petrol",
        "two_wheeler_electric",
        "four_wheeler_petrol",
        "four_wheeler_electric",
        "walking",
        "wfh",
    }
)
"""Exact set of transport mode keys that must appear in ``transport_factors.json``."""

EXPECTED_FOOD_CATEGORIES: frozenset[str] = frozenset(
    {
        "veg_meal",
        "non_veg_meal_chicken",
        "non_veg_meal_mutton",
        "non_veg_meal_fish",
        "egg_single",
        "dairy_serving_250ml",
        "paneer_serving_100g",
        "dal_serving",
        "rice_serving",
        "snack_processed",
    }
)
"""Exact set of food category keys that must appear in ``food_factors.json``."""

_MIN_SOURCE_LEN: int = 10


def _load_and_check_common(path: Path, expected_unit: str) -> dict[str, Any]:
    """Parse a factor JSON file and enforce top-level and per-entry invariants.

    Checks performed on every file:

    1. JSON is parseable.
    2. ``schema_version`` key is present and non-empty.
    3. ``unit`` key matches *expected_unit*.
    4. Every entry under ``"entries"`` passes :class:`~app.models.emission.FactorEntry`
       validation.
    5. Every entry's ``source`` is at least :data:`_MIN_SOURCE_LEN` characters.
    6. Every entry with ``confidence == "estimated"`` has non-empty ``notes``.

    Args:
        path: Absolute path to the JSON data file.
        expected_unit: Expected value of the top-level ``"unit"`` key.

    Returns:
        The ``"entries"`` sub-dict as ``dict[str, Any]``.

    Raises:
        AssertionError: On any invariant violation; the message names the
            failing file and key.
    """
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"{path.name}: cannot parse JSON — {exc}") from exc

    if not raw.get("schema_version"):
        raise AssertionError(f"{path.name}: missing or empty 'schema_version'")

    unit = raw.get("unit")
    if unit != expected_unit:
        raise AssertionError(f"{path.name}: expected unit '{expected_unit}', got '{unit}'")

    entries: dict[str, Any] = raw.get("entries", {})
    if not isinstance(entries, dict):
        raise AssertionError(f"{path.name}: 'entries' must be a JSON object")

    for key, data in entries.items():
        try:
            entry: FactorEntry = FactorEntry.model_validate(data)
        except Exception as exc:
            raise AssertionError(
                f"{path.name}: entry '{key}' failed FactorEntry validation — {exc}"
            ) from exc

        if len(entry.source) < _MIN_SOURCE_LEN:
            raise AssertionError(
                f"{path.name}: entry '{key}' source is too short "
                f"(< {_MIN_SOURCE_LEN} chars): '{entry.source}'"
            )

        if entry.confidence == "estimated" and not entry.notes:
            raise AssertionError(
                f"{path.name}: entry '{key}' has confidence='estimated' "
                f"but notes is null or empty"
            )

    return entries


def check_grid_factors(path: Path | None = None) -> None:
    """Assert that ``state_grid_factors.json`` is complete and valid.

    In addition to the common checks (see :func:`_load_and_check_common`),
    verifies that every :class:`~app.models.user.IndianState` enum value has
    exactly one entry and that no extra keys are present.

    Args:
        path: Override file path.  Defaults to
            ``app/data/state_grid_factors.json`` relative to the repo root.

    Raises:
        AssertionError: On any invariant violation.
    """
    resolved = path or (_DATA_DIR / "state_grid_factors.json")
    entries = _load_and_check_common(resolved, _EXPECTED_GRID_UNIT)

    all_state_values = {s.value for s in IndianState}
    entry_keys = set(entries.keys())

    missing = all_state_values - entry_keys
    if missing:
        raise AssertionError(
            f"state_grid_factors.json: missing entries for states: {sorted(missing)}"
        )

    extra = entry_keys - all_state_values
    if extra:
        raise AssertionError(f"state_grid_factors.json: unexpected extra keys: {sorted(extra)}")


def check_transport_factors(path: Path | None = None) -> None:
    """Assert that ``transport_factors.json`` is complete and valid.

    In addition to the common checks, verifies that the mode keys match
    :data:`EXPECTED_TRANSPORT_MODES` exactly (no missing, no extras).

    Args:
        path: Override file path.  Defaults to
            ``app/data/transport_factors.json`` relative to the repo root.

    Raises:
        AssertionError: On any invariant violation.
    """
    resolved = path or (_DATA_DIR / "transport_factors.json")
    entries = _load_and_check_common(resolved, _EXPECTED_TRANSPORT_UNIT)

    entry_keys = set(entries.keys())

    missing = EXPECTED_TRANSPORT_MODES - entry_keys
    if missing:
        raise AssertionError(f"transport_factors.json: missing mode keys: {sorted(missing)}")

    extra = entry_keys - EXPECTED_TRANSPORT_MODES
    if extra:
        raise AssertionError(f"transport_factors.json: unexpected extra keys: {sorted(extra)}")


def check_food_factors(path: Path | None = None) -> None:
    """Assert that ``food_factors.json`` is complete and valid.

    In addition to the common checks, verifies that the category keys match
    :data:`EXPECTED_FOOD_CATEGORIES` exactly (no missing, no extras).

    Args:
        path: Override file path.  Defaults to
            ``app/data/food_factors.json`` relative to the repo root.

    Raises:
        AssertionError: On any invariant violation.
    """
    resolved = path or (_DATA_DIR / "food_factors.json")
    entries = _load_and_check_common(resolved, _EXPECTED_FOOD_UNIT)

    entry_keys = set(entries.keys())

    missing = EXPECTED_FOOD_CATEGORIES - entry_keys
    if missing:
        raise AssertionError(f"food_factors.json: missing category keys: {sorted(missing)}")

    extra = entry_keys - EXPECTED_FOOD_CATEGORIES
    if extra:
        raise AssertionError(f"food_factors.json: unexpected extra keys: {sorted(extra)}")


def main() -> None:
    """Run all three data-file checks and exit with code 0 or 1.

    Prints ``"OK: <filename>"`` to stdout for each passing check.  On the
    first failure, prints the error message to ``stderr`` and exits with
    code 1.
    """
    checks = [
        ("state_grid_factors.json", check_grid_factors),
        ("transport_factors.json", check_transport_factors),
        ("food_factors.json", check_food_factors),
    ]
    for filename, fn in checks:
        try:
            fn()
            print(f"OK: {filename}")
        except AssertionError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
