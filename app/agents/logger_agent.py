"""Logger agent: natural-language carbon activity capture via Gemini 2.5 Flash.

The :class:`LoggerAgent` converts a single free-text activity description into a
validated :class:`~app.models.activity.Activity` carrying a visible reasoning
trace.  Gemini is used **only** for natural-language extraction through function
calling; every emission figure is computed deterministically against the
:class:`~app.services.emission_service.EmissionService`, never by the model.

Results are returned as the typed :data:`LoggerOutcome` discriminated union so
that governance rejections and model failures are ordinary values rather than
exceptions, letting the API layer branch on ``status`` without ``try``/``except``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Literal

from google.generativeai.protos import Tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.base import BaseAgent
from app.agents.prompts.logger_v1 import (
    FUNCTION_DECLARATIONS,
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
)
from app.core.gemini import GenerativeModelFactory
from app.models.activity import (
    Activity,
    ActivityType,
    ElectricityData,
    FoodData,
    TransportData,
)
from app.models.shared import AgentReasoning, Confidence
from app.models.user import IndianState
from app.services.emission_service import EmissionService

_GEMINI_TIMEOUT_S: Final[float] = 8.0
"""Maximum seconds to await a single Gemini generation before failing."""

AVG_INR_PER_KWH: Final[float] = 8.0
"""Indian urban metro residential weighted average all-in tariff (₹/kWh).

Used only when the user provides bill amount in INR without explicit kWh.
Tariffs vary by state, slab, and consumption tier; this is intentionally
a national rough average. Any Activity derived using this constant must
set confidence='estimated' regardless of grid factor confidence.
"""

_FUNCTION_TO_TYPE: Final[dict[str, ActivityType]] = {
    "log_transport": "transport",
    "log_electricity": "electricity",
    "log_food": "food",
}
"""Maps each Gemini function name to its activity type."""

_INPUT_SUMMARY_LIMIT: Final[int] = 120
"""Maximum length of the reasoning input summary."""


class LoggerSuccess(BaseModel):
    """A successfully captured activity.

    Attributes:
        status: Discriminator literal ``"success"``.
        activity: The fully-formed, persistence-ready activity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["success"] = "success"
    activity: Activity


class LoggerRejected(BaseModel):
    """Input rejected by governance before any model call.

    Attributes:
        status: Discriminator literal ``"rejected"``.
        reason: Human-readable rejection explanation.
        category: Governance category (e.g. ``"injection"``, ``"off_topic"``).
        agent_reasoning: Reasoning trace describing the rejection.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["rejected"] = "rejected"
    reason: str
    category: str
    agent_reasoning: AgentReasoning


class LoggerFailed(BaseModel):
    """The model call or its output could not be turned into an activity.

    Attributes:
        status: Discriminator literal ``"failed"``.
        reason: Human-readable failure explanation.
        agent_reasoning: Reasoning trace describing the failure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["failed"] = "failed"
    reason: str
    agent_reasoning: AgentReasoning


LoggerOutcome = Annotated[
    LoggerSuccess | LoggerRejected | LoggerFailed,
    Field(discriminator="status"),
]
"""Discriminated union of every possible Logger result, keyed on ``status``."""


def _summarise(text: str, *, limit: int = _INPUT_SUMMARY_LIMIT) -> str:
    """Collapse whitespace and bound the length of a text summary.

    Args:
        text: Raw text to summarise.
        limit: Maximum length of the returned string.

    Returns:
        A single-line summary no longer than ``limit`` characters.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


def _extract_function_call(response: Any) -> Any | None:
    """Return the first non-empty function call in a Gemini response.

    Args:
        response: The object returned by ``generate_content_async``.

    Returns:
        The first ``FunctionCall`` with a non-empty name, or ``None`` if the
        response contains no usable function call.
    """
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            function_call = getattr(part, "function_call", None)
            if function_call is not None and getattr(function_call, "name", None):
                return function_call
    return None


class LoggerAgent(BaseAgent):
    """Captures one carbon activity from a natural-language description.

    Gemini Flash extracts the structured fields via function calling; emission
    arithmetic is performed locally against the injected emission service.

    Args:
        emission_service: Provides emission-factor lookups.
        gemini_factory: Builds the configured Gemini Flash model.
    """

    def __init__(
        self,
        *,
        emission_service: EmissionService,
        gemini_factory: GenerativeModelFactory,
    ) -> None:
        """Build and cache the configured Flash model and store dependencies."""
        model = gemini_factory.flash(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[Tool(function_declarations=FUNCTION_DECLARATIONS)],
        )
        super().__init__(prompt_version=PROMPT_VERSION, model_name=str(model.model_name))
        self._emission_service = emission_service
        self._model = model

    async def log_activity(
        self,
        *,
        user_input: str,
        user_state: IndianState,
        activity_id: str,
        user_id: str,
        now: datetime | None = None,
    ) -> LoggerOutcome:
        """Capture a single activity from free-text user input.

        Args:
            user_input: The raw activity description typed by the user.
            user_state: The user's state, used for the electricity grid factor.
            activity_id: Client-assigned UUID for the resulting activity.
            user_id: Firebase UID of the owning user.
            now: Override for the activity timestamp (defaults to current UTC).

        Returns:
            A :data:`LoggerOutcome`: :class:`LoggerSuccess` on capture,
            :class:`LoggerRejected` when governance blocks the input, or
            :class:`LoggerFailed` when the model call or its output is unusable.
        """
        start = self._now_ms()
        steps: list[str] = []

        governance_result = self._check_governance(user_input)
        if not governance_result.allowed:
            steps.append(f"Governance blocked input as '{governance_result.category}'.")
            reasoning = self._build_reasoning(
                agent_name="logger",
                input_summary=_summarise(user_input),
                steps=steps,
                output_summary=f"Rejected ({governance_result.category}).",
                latency_ms=self._now_ms() - start,
            )
            self._log("logger.rejected", category=governance_result.category)
            return LoggerRejected(
                reason=governance_result.reason or "Input rejected by governance.",
                category=governance_result.category,
                agent_reasoning=reasoning,
            )
        steps.append("Governance check passed.")

        try:
            response = await asyncio.wait_for(
                self._model.generate_content_async(user_input),
                timeout=_GEMINI_TIMEOUT_S,
            )
        except TimeoutError:
            return self._failed(
                "Gemini call timed out.",
                user_input,
                [*steps, "Model call timed out."],
                start,
            )
        except Exception as exc:
            return self._failed(
                f"Gemini call failed: {exc}",
                user_input,
                [*steps, "Model call raised an error."],
                start,
            )
        steps.append("Received model response.")

        function_call = _extract_function_call(response)
        if function_call is None:
            return self._failed(
                "Model did not return a function call.",
                user_input,
                [*steps, "Response contained no function call."],
                start,
            )

        function_name = str(function_call.name)
        activity_type = _FUNCTION_TO_TYPE.get(function_name)
        if activity_type is None:
            return self._failed(
                f"Model returned an unknown function '{function_name}'.",
                user_input,
                [*steps, f"Unknown function '{function_name}'."],
                start,
            )
        steps.append(f"Model selected '{function_name}'.")

        raw_args: dict[str, Any] = dict(function_call.args)

        emission_kg: float
        confidence: Confidence
        source: str
        structured: dict[str, Any]

        if activity_type == "transport":
            try:
                transport = TransportData.model_validate(raw_args)
            except ValidationError:
                return self._failed(
                    "Model returned invalid transport fields.",
                    user_input,
                    [*steps, "Transport validation failed."],
                    start,
                )
            transport_factor = self._emission_service.get_transport_factor(transport.mode)
            if transport_factor is None:
                return self._failed(
                    f"Unknown transport mode '{transport.mode}'.",
                    user_input,
                    [*steps, f"No emission factor for mode '{transport.mode}'."],
                    start,
                )
            emission_kg = round(transport_factor.entry.value * transport.km, 4)
            confidence = transport_factor.entry.confidence
            source = transport_factor.entry.source
            structured = transport.model_dump()
            steps.append(
                f"mode '{transport.mode}' "
                f"({transport_factor.entry.value} kg/km) x {transport.km} km "
                f"= {emission_kg} kg CO2e."
            )
        elif activity_type == "electricity":
            try:
                electricity = ElectricityData.model_validate(raw_args)
            except ValidationError:
                return self._failed(
                    "Model returned invalid electricity fields.",
                    user_input,
                    [*steps, "Electricity validation failed."],
                    start,
                )
            grid = self._emission_service.get_grid_factor(user_state)
            if electricity.kwh is not None:
                kwh = electricity.kwh
                electricity_data = electricity
                confidence = grid.entry.confidence
            else:
                bill = electricity.bill_amount_inr or 0.0
                kwh = round(bill / AVG_INR_PER_KWH, 4)
                note = f"kWh derived from ₹{bill} at {AVG_INR_PER_KWH} INR/kWh assumption."
                electricity_data = electricity.model_copy(update={"kwh": kwh, "notes": note})
                confidence = "estimated"
                steps.append(note)
            emission_kg = round(grid.entry.value * kwh, 4)
            source = grid.entry.source
            structured = electricity_data.model_dump()
            steps.append(
                f"{user_state.value} grid "
                f"({grid.entry.value} kg/kWh) x {kwh} kWh "
                f"= {emission_kg} kg CO2e."
            )
        else:
            try:
                food = FoodData.model_validate(raw_args)
            except ValidationError:
                return self._failed(
                    "Model returned invalid food fields.",
                    user_input,
                    [*steps, "Food validation failed."],
                    start,
                )
            food_factor = self._emission_service.get_food_factor(food.category)
            if food_factor is None:
                return self._failed(
                    f"Unknown food category '{food.category}'.",
                    user_input,
                    [*steps, f"No emission factor for category '{food.category}'."],
                    start,
                )
            emission_kg = round(food_factor.entry.value * food.servings, 4)
            confidence = food_factor.entry.confidence
            source = food_factor.entry.source
            structured = food.model_dump()
            steps.append(
                f"category '{food.category}' "
                f"({food_factor.entry.value} kg/serving) x {food.servings} servings "
                f"= {emission_kg} kg CO2e."
            )

        reasoning = self._build_reasoning(
            agent_name="logger",
            input_summary=_summarise(user_input),
            steps=steps,
            output_summary=f"{activity_type}: {emission_kg} kg CO2e ({confidence}).",
            latency_ms=self._now_ms() - start,
        )
        activity = Activity(
            id=activity_id,
            user_id=user_id,
            type=activity_type,
            timestamp=now if now is not None else datetime.now(tz=UTC),
            raw_input=user_input,
            structured_data=structured,
            emission_kg_co2e=emission_kg,
            confidence=confidence,
            emission_factor_source=source,
            agent_reasoning=reasoning,
        )
        self._log("logger.success", activity_type=activity_type, emission_kg=emission_kg)
        return LoggerSuccess(activity=activity)

    def _failed(
        self,
        reason: str,
        user_input: str,
        steps: list[str],
        start_ms: int,
    ) -> LoggerFailed:
        """Assemble a :class:`LoggerFailed` outcome with a reasoning trace.

        Args:
            reason: Human-readable failure explanation.
            user_input: The original user input, for the input summary.
            steps: Reasoning steps accumulated up to the failure.
            start_ms: The ``_now_ms`` value captured at the start of the run.

        Returns:
            A populated :class:`LoggerFailed`.
        """
        reasoning = self._build_reasoning(
            agent_name="logger",
            input_summary=_summarise(user_input),
            steps=steps,
            output_summary=f"Failed: {reason}",
            latency_ms=self._now_ms() - start_ms,
        )
        self._log("logger.failed", reason=reason)
        return LoggerFailed(reason=reason, agent_reasoning=reasoning)
