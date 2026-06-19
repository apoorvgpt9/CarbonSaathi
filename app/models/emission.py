"""Emission factor domain models for CarbonSaathi.

Defines :class:`FactorEntry`, the atomic schema for a single emission factor
record loaded from the JSON data files, and :class:`FactorLookupResult`, the
typed envelope returned by
:class:`~app.services.emission_service.EmissionService` lookup methods.

The :data:`~app.models.shared.Confidence` literal is re-used from
:mod:`app.models.shared` so that all confidence classifications across the
codebase share a single source of truth.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.shared import Confidence


class FactorEntry(BaseModel):
    """Atomic emission factor record loaded from a JSON data file.

    All instances are immutable (``frozen=True``) and reject unknown fields
    (``extra="forbid"``) so that schema drift in the data files is caught at
    application startup.

    Attributes:
        value: Emission factor magnitude in the declared unit (≥ 0).
        unit: Denominator unit string, e.g. ``"kg_co2e_per_kwh"``.
        source: Citation string identifying the data origin (≥ 10 chars enforced
            by the verification script).
        confidence: Reliability classification of this estimate.
        last_verified: Date the entry was last cross-checked against the source.
        notes: Optional free-text clarifications.  Required by the verification
            script for all entries with ``confidence == "estimated"``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float = Field(ge=0, description="Emission factor magnitude (≥ 0)")
    unit: str = Field(min_length=1, description="Denominator unit string")
    source: str = Field(min_length=1, description="Citation for the data origin")
    confidence: Confidence
    last_verified: date
    notes: str | None = None


class FactorLookupResult(BaseModel):
    """Result envelope for a single emission factor lookup.

    Wraps a :class:`FactorEntry` with the resolved lookup key so that callers
    do not need to repeat the key after the lookup.

    Attributes:
        key: The resolved lookup key, e.g. ``"Delhi"``, ``"metro"``,
            ``"veg_meal"``.
        entry: The validated emission factor entry.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    entry: FactorEntry
