"""Activity domain model for CarbonSaathi.

An :class:`Activity` represents a single carbon-emitting action logged by the
user (transport, electricity, or food).  It is written to
``users/{uid}/activities/{id}`` in Firestore by the Logger agent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.shared import AgentReasoning, IsoTimestamp
from app.models.shared import Confidence as Confidence

ActivityType = Literal["transport", "electricity", "food"]
"""Category of carbon-emitting activity."""


class Activity(BaseModel):
    """A single logged carbon-emitting event.

    Attributes:
        id: Client-assigned UUID (used as the Firestore document ID).
        user_id: Firebase UID of the owning user.
        type: Broad category of the activity.
        timestamp: When the activity occurred (UTC, timezone-aware).
        raw_input: Verbatim text submitted by the user (1-500 chars).
        structured_data: Agent-parsed key/value pairs (schema varies by type).
        emission_kg_co2e: Calculated emission in kg CO₂e (≥ 0, 4-decimal precision recommended).
        confidence: Reliability of the emission value.
        emission_factor_source: Citation string for the factor used (e.g. ``"CEA 2023"``)
        agent_reasoning: Full reasoning trace from the Logger agent; ``None`` if
            the activity was created programmatically without an agent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    user_id: str
    type: ActivityType
    timestamp: IsoTimestamp
    raw_input: str = Field(min_length=1, max_length=500)
    structured_data: dict[str, Any]
    emission_kg_co2e: float = Field(ge=0, description="kg CO2e, 4-decimal precision recommended")
    confidence: Confidence
    emission_factor_source: str = Field(min_length=1)
    agent_reasoning: AgentReasoning | None = None


class TransportData(BaseModel):
    """Structured fields extracted by the Logger for a transport activity.

    Validated before being serialised into :attr:`Activity.structured_data`.

    Attributes:
        mode: Transport mode key matching a ``transport_factors.json`` entry.
        km: Distance travelled in kilometres (0-10000).
        notes: Optional free-text caveats captured by the agent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: str = Field(min_length=1)
    km: float = Field(ge=0, le=10000)
    notes: str | None = None


class ElectricityData(BaseModel):
    """Structured fields extracted by the Logger for an electricity activity.

    At least one of ``kwh`` or ``bill_amount_inr`` must be provided.  When only
    a bill amount is supplied, the Logger derives ``kwh`` from it and records the
    assumption in ``notes``.

    Attributes:
        kwh: Energy consumed in kWh, if known or derived (≥ 0).
        appliance: Optional appliance name the usage relates to.
        hours: Optional hours of operation (≥ 0).
        bill_amount_inr: Optional monthly bill amount in INR (≥ 0).
        notes: Optional free-text caveats (e.g. the kWh-from-bill assumption).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kwh: float | None = Field(default=None, ge=0)
    appliance: str | None = None
    hours: float | None = Field(default=None, ge=0)
    bill_amount_inr: float | None = Field(default=None, ge=0)
    notes: str | None = None

    @model_validator(mode="after")
    def _require_kwh_or_bill(self) -> ElectricityData:
        """Ensure at least one usage source is present.

        Returns:
            The validated model.

        Raises:
            ValueError: If both ``kwh`` and ``bill_amount_inr`` are ``None``.
        """
        if self.kwh is None and self.bill_amount_inr is None:
            raise ValueError("at least one of kwh or bill_amount_inr must be provided")
        return self


class FoodData(BaseModel):
    """Structured fields extracted by the Logger for a food activity.

    Attributes:
        category: Food category key matching a ``food_factors.json`` entry.
        servings: Number of servings consumed (> 0, ≤ 20).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(min_length=1)
    servings: float = Field(gt=0, le=20)
