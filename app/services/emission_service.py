"""Emission factor lookup service for CarbonSaathi.

Loads the three emission-factor JSON data files at construction time,
validates every entry against :class:`~app.models.emission.FactorEntry`,
and exposes typed lookup methods for grid, transport, and food factors.

All lookup methods are pure in-memory dict operations; no I/O occurs after
the constructor returns.  Use :func:`get_emission_service` to obtain the
process-wide singleton.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.models.emission import FactorEntry, FactorLookupResult
from app.models.user import IndianState

_DATA_DIR: Path = Path(__file__).parent.parent / "data"
"""Absolute path to the ``app/data/`` directory containing the JSON factor files."""


class EmissionDataError(Exception):
    """Raised when an emission factor JSON file fails to load or validate.

    Attributes:
        message: Human-readable description of what went wrong.
    """


class EmissionService:
    """Loads and caches all emission factor datasets in memory.

    Each dataset (state electricity grid, transport, food) is loaded once at
    construction from JSON files under ``app/data/``.  All public methods are
    pure dict lookups — no further I/O occurs after the constructor returns.

    Args:
        grid_path: Override path for ``state_grid_factors.json``.  Defaults to
            the bundled data file under ``app/data/``.
        transport_path: Override path for ``transport_factors.json``.
        food_path: Override path for ``food_factors.json``.

    Raises:
        EmissionDataError: If any JSON file cannot be read, parsed, or if any
            entry fails :class:`~app.models.emission.FactorEntry` validation.
    """

    def __init__(
        self,
        grid_path: Path | None = None,
        transport_path: Path | None = None,
        food_path: Path | None = None,
    ) -> None:
        """Load and validate all three emission factor datasets."""
        self._grid: dict[str, FactorEntry] = self._load(
            grid_path or (_DATA_DIR / "state_grid_factors.json")
        )
        self._transport: dict[str, FactorEntry] = self._load(
            transport_path or (_DATA_DIR / "transport_factors.json")
        )
        self._food: dict[str, FactorEntry] = self._load(
            food_path or (_DATA_DIR / "food_factors.json")
        )

    @staticmethod
    def _load(path: Path) -> dict[str, FactorEntry]:
        """Parse a factor JSON file and validate every entry with Pydantic.

        Args:
            path: Absolute path to the JSON data file.

        Returns:
            Mapping of entry key strings to validated
            :class:`~app.models.emission.FactorEntry` objects.

        Raises:
            EmissionDataError: If the file cannot be read, the JSON is
                malformed, or any entry fails schema validation.
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EmissionDataError(f"Failed to load {path.name}: {exc}") from exc

        entries: dict[str, FactorEntry] = {}
        for key, data in raw.get("entries", {}).items():
            try:
                entries[str(key)] = FactorEntry.model_validate(data)
            except Exception as exc:
                raise EmissionDataError(f"Invalid entry '{key}' in {path.name}: {exc}") from exc

        return entries

    def get_grid_factor(self, state: IndianState) -> FactorLookupResult:
        """Return the grid emission factor for an Indian state or Union Territory.

        Args:
            state: An :class:`~app.models.user.IndianState` enum member.

        Returns:
            :class:`~app.models.emission.FactorLookupResult` with the resolved
            state name as ``key`` and the validated factor as ``entry``.

        Raises:
            KeyError: If the state has no entry in the loaded dataset.  This
                indicates a data-integrity bug that the verification script
                should have caught.
        """
        key = state.value
        return FactorLookupResult(key=key, entry=self._grid[key])

    def get_transport_factor(self, mode: str) -> FactorLookupResult | None:
        """Return the transport emission factor for a mode key, or ``None``.

        Args:
            mode: Transport mode key (e.g. ``"metro"``, ``"taxi_petrol"``).

        Returns:
            :class:`~app.models.emission.FactorLookupResult` if the mode is
            recognised, ``None`` otherwise.  Callers decide how to handle an
            unknown mode (e.g. fall back to a default, surface an error).
        """
        entry = self._transport.get(mode)
        if entry is None:
            return None
        return FactorLookupResult(key=mode, entry=entry)

    def get_food_factor(self, category: str) -> FactorLookupResult | None:
        """Return the food emission factor for a category key, or ``None``.

        Args:
            category: Food category key (e.g. ``"veg_meal"``, ``"egg_single"``).

        Returns:
            :class:`~app.models.emission.FactorLookupResult` if the category is
            recognised, ``None`` otherwise.
        """
        entry = self._food.get(category)
        if entry is None:
            return None
        return FactorLookupResult(key=category, entry=entry)

    def list_transport_modes(self) -> list[str]:
        """Return a sorted list of all valid transport mode keys.

        Returns:
            Alphabetically sorted list of mode key strings.
        """
        return sorted(self._transport.keys())

    def list_food_categories(self) -> list[str]:
        """Return a sorted list of all valid food category keys.

        Returns:
            Alphabetically sorted list of category key strings.
        """
        return sorted(self._food.keys())


@lru_cache(maxsize=1)
def get_emission_service() -> EmissionService:
    """Return the process-wide singleton :class:`EmissionService` instance.

    Uses the default data paths under ``app/data/``.  The result is cached
    after the first call; all subsequent calls return the same object with no
    additional file I/O.

    Returns:
        The cached :class:`EmissionService` instance.
    """
    return EmissionService()
