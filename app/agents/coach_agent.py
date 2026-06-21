"""Coach agent: proposes carbon-reduction recommendations via Gemini 2.5 Flash.

The :class:`CoachAgent` turns a user's profile, recent activities, and the
Analyst's insights into :class:`~app.models.recommendation.Recommendation`
objects, each with a visible reasoning trace.  Gemini proposes a typed
``saving_basis`` for every recommendation; the agent then computes the emission
saving **deterministically** from the
:class:`~app.services.emission_service.EmissionService` — the model never reports
a saving figure itself.  Recommendations whose basis is invalid or yields no
meaningful saving are dropped.

Results are returned as the typed :data:`CoachOutcome` discriminated union.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated, Final, Literal
from uuid import uuid4

import google.generativeai as genai
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.analyst_agent import bucket_by_week
from app.agents.base import BaseAgent
from app.agents.prompts.coach_v1 import (
    PROMPT_VERSION,
    RESPONSE_SCHEMA,
    SYSTEM_INSTRUCTION,
    build_user_prompt,
)
from app.core.gemini import GenerativeModelFactory
from app.models.activity import Activity
from app.models.insight import Insight
from app.models.recommendation import Difficulty, Recommendation, RecType
from app.models.shared import AgentReasoning
from app.models.user import IndianState, UserProfile
from app.services.emission_service import EmissionService

_GEMINI_TIMEOUT_S: Final[float] = 30.0
"""Maximum seconds to await a single Gemini Flash generation before failing."""

_MAX_RECOMMENDATIONS: Final[int] = 3
"""Upper bound on recommendations returned from a single coaching pass."""

_MIN_MEANINGFUL_SAVING_KG: Final[float] = 0.01
"""Computed weekly savings below this (kg CO2e) are not worth recommending."""

_INPUT_SUMMARY_LIMIT: Final[int] = 120
"""Maximum length of the reasoning input summary."""


class TransportSwapBasis(BaseModel):
    """Saving basis for replacing one transport mode with a cleaner one.

    Attributes:
        kind: Discriminator literal ``"transport_swap"``.
        from_mode: Higher-emission transport mode key being replaced.
        to_mode: Lower-emission transport mode key adopted instead.
        weekly_km: Distance shifted per week in kilometres (0 < km <= 2000).
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["transport_swap"]
    from_mode: str = Field(min_length=1)
    to_mode: str = Field(min_length=1)
    weekly_km: float = Field(gt=0, le=2000)


class ElectricityReduceBasis(BaseModel):
    """Saving basis for cutting weekly electricity consumption.

    Attributes:
        kind: Discriminator literal ``"electricity_reduce"``.
        weekly_kwh_reduction: kWh avoided per week (0 < kwh <= 200).
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["electricity_reduce"]
    weekly_kwh_reduction: float = Field(gt=0, le=200)


class FoodSwapBasis(BaseModel):
    """Saving basis for replacing one food choice with a cleaner one.

    Attributes:
        kind: Discriminator literal ``"food_swap"``.
        from_category: Higher-emission food category key being replaced.
        to_category: Lower-emission food category key adopted instead.
        weekly_meals: Meals swapped per week (0 < meals <= 21).
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["food_swap"]
    from_category: str = Field(min_length=1)
    to_category: str = Field(min_length=1)
    weekly_meals: float = Field(gt=0, le=21)


SavingBasis = Annotated[
    TransportSwapBasis | ElectricityReduceBasis | FoodSwapBasis,
    Field(discriminator="kind"),
]
"""Discriminated union of the three supported saving bases, keyed on ``kind``."""


class _RecDraft(BaseModel):
    """Validation shell for one model-proposed recommendation.

    Uses ``extra="ignore"`` because the value is untrusted model output.  The
    ``expected_saving_kg`` is never read from the model: the agent computes it
    from ``saving_basis``.

    Attributes:
        type: The recommendation category.
        title: Short heading (1-200 chars).
        description: Explanation (1-2000 chars).
        difficulty: Estimated adoption effort.
        saving_basis: The typed basis used to compute the saving.
    """

    model_config = ConfigDict(extra="ignore")

    type: RecType
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    difficulty: Difficulty
    saving_basis: SavingBasis


def _evaluate_basis(
    basis: SavingBasis,
    *,
    emission_service: EmissionService,
    state: IndianState,
) -> tuple[float | None, str]:
    """Compute the deterministic weekly saving for a saving basis.

    Args:
        basis: The validated saving basis to evaluate.
        emission_service: Source of emission factors.
        state: The user's state, used for the electricity grid factor.

    Returns:
        A ``(saving, note)`` pair.  ``saving`` is the weekly saving in kg CO2e
        rounded to 4 decimals, or ``None`` when the basis references unknown
        factors, would not actually save emissions, or falls below the
        meaningful-saving threshold; ``note`` explains the computation or the
        reason for rejection.
    """
    if isinstance(basis, TransportSwapBasis):
        from_factor = emission_service.get_transport_factor(basis.from_mode)
        to_factor = emission_service.get_transport_factor(basis.to_mode)
        if from_factor is None or to_factor is None:
            return None, f"unknown transport mode ({basis.from_mode} -> {basis.to_mode})"
        if from_factor.entry.value <= to_factor.entry.value:
            return None, f"transport_swap saves nothing ({basis.from_mode} <= {basis.to_mode})"
        saving = (from_factor.entry.value - to_factor.entry.value) * basis.weekly_km
        note = (
            f"transport_swap {basis.from_mode}->{basis.to_mode}: "
            f"({from_factor.entry.value}-{to_factor.entry.value}) x {basis.weekly_km} km/wk"
        )
    elif isinstance(basis, ElectricityReduceBasis):
        grid = emission_service.get_grid_factor(state)
        saving = grid.entry.value * basis.weekly_kwh_reduction
        note = f"electricity_reduce: {grid.entry.value} x " f"{basis.weekly_kwh_reduction} kWh/wk"
    else:
        from_food = emission_service.get_food_factor(basis.from_category)
        to_food = emission_service.get_food_factor(basis.to_category)
        if from_food is None or to_food is None:
            return None, f"unknown food category ({basis.from_category} -> {basis.to_category})"
        if from_food.entry.value <= to_food.entry.value:
            return None, f"food_swap saves nothing ({basis.from_category} <= {basis.to_category})"
        saving = (from_food.entry.value - to_food.entry.value) * basis.weekly_meals
        note = (
            f"food_swap {basis.from_category}->{basis.to_category}: "
            f"({from_food.entry.value}-{to_food.entry.value}) x {basis.weekly_meals} meals/wk"
        )

    saving = round(saving, 4)
    if saving < _MIN_MEANINGFUL_SAVING_KG:
        return None, f"saving {saving} kg below threshold"
    return saving, f"{note} = {saving} kg/wk"


class CoachSuccess(BaseModel):
    """One or more recommendations produced for the user.

    Attributes:
        status: Discriminator literal ``"success"``.
        recommendations: The generated recommendations (at least one).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["success"] = "success"
    recommendations: list[Recommendation]


class CoachEmpty(BaseModel):
    """The Coach ran cleanly but produced no grounded recommendation.

    Attributes:
        status: Discriminator literal ``"empty"``.
        reason: Human-readable explanation.
        agent_reasoning: Reasoning trace describing the outcome.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["empty"] = "empty"
    reason: str
    agent_reasoning: AgentReasoning


class CoachFailed(BaseModel):
    """The model call failed or returned unusable output.

    Attributes:
        status: Discriminator literal ``"failed"``.
        reason: Human-readable failure explanation.
        agent_reasoning: Reasoning trace describing the failure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["failed"] = "failed"
    reason: str
    agent_reasoning: AgentReasoning


CoachOutcome = Annotated[
    CoachSuccess | CoachEmpty | CoachFailed,
    Field(discriminator="status"),
]
"""Discriminated union of every possible Coach result, keyed on ``status``."""


class CoachAgent(BaseAgent):
    """Proposes personalised carbon-reduction recommendations.

    Gemini Pro proposes a typed ``saving_basis`` per recommendation; the agent
    computes the saving deterministically from the emission service.

    Args:
        emission_service: Provides emission-factor lookups for saving maths.
        gemini_factory: Builds the configured Gemini Pro model.
        user_state: Optional fallback state retained for callers that construct
            the agent per-user; the per-call ``profile.state`` is authoritative.
    """

    def __init__(
        self,
        *,
        emission_service: EmissionService,
        gemini_factory: GenerativeModelFactory,
        user_state: IndianState | None = None,
    ) -> None:
        """Build and cache the configured Flash model and JSON generation config."""
        model = gemini_factory.flash(system_instruction=SYSTEM_INSTRUCTION)
        super().__init__(prompt_version=PROMPT_VERSION, model_name=str(model.model_name))
        self._model = model
        self._emission_service = emission_service
        self._user_state = user_state
        self._generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        )

    async def generate_recommendations(
        self,
        *,
        profile: UserProfile,
        activities: list[Activity],
        insights: list[Insight],
        user_id: str,
        now: datetime | None = None,
    ) -> CoachOutcome:
        """Produce grounded recommendations for a user.

        Args:
            profile: The user's profile, used to personalise advice and select
                the electricity grid factor.
            activities: The user's recent activities (emission context).
            insights: The Analyst's insights, used as additional context.
            user_id: Firebase UID of the owning user.
            now: Override for the recommendation timestamp and bucketing
                reference (defaults to the current UTC time).

        Returns:
            A :data:`CoachOutcome`: :class:`CoachSuccess` with at least one
            recommendation, :class:`CoachEmpty` when none is grounded, or
            :class:`CoachFailed` on a model error or malformed output.
        """
        start = self._now_ms()
        moment = now if now is not None else datetime.now(tz=UTC)
        steps: list[str] = []

        if profile.state is None or profile.home_profile is None:
            return CoachEmpty(
                reason="Complete onboarding (state and home profile) to get recommendations.",
                agent_reasoning=self._reasoning(
                    input_summary=f"{len(activities)} activities; user not onboarded.",
                    steps=["User has no state or home profile; onboarding incomplete."],
                    output_summary="No recommendations (onboarding incomplete).",
                    start=start,
                ),
            )
        state = profile.state
        home = profile.home_profile

        buckets = bucket_by_week(activities, now=moment)
        prompt = build_user_prompt(state, home, buckets, insights)
        input_summary = f"{len(activities)} activities; {len(insights)} insights; {state.value}."

        try:
            response = await asyncio.wait_for(
                self._model.generate_content_async(
                    prompt, generation_config=self._generation_config
                ),
                timeout=_GEMINI_TIMEOUT_S,
            )
        except TimeoutError:
            return self._failed(
                "Gemini call timed out.",
                input_summary,
                [*steps, "Model call timed out."],
                start,
            )
        except Exception as exc:
            return self._failed(
                f"Gemini call failed: {exc}",
                input_summary,
                [*steps, "Model call raised an error."],
                start,
            )

        try:
            payload = json.loads(response.text)
            raw_recs = payload["recommendations"]
            if not isinstance(raw_recs, list):
                raise TypeError("'recommendations' must be a list")
        except (ValueError, KeyError, TypeError):
            return self._failed(
                "Model returned malformed JSON.",
                input_summary,
                [*steps, "Could not parse model JSON."],
                start,
            )
        steps.append(f"Model returned {len(raw_recs)} recommendation draft(s).")

        kept: list[tuple[_RecDraft, float]] = []
        for draft_data in raw_recs:
            if len(kept) >= _MAX_RECOMMENDATIONS:
                break
            try:
                draft = _RecDraft.model_validate(draft_data)
            except ValidationError:
                steps.append("Dropped rec: invalid fields.")
                continue
            saving, note = _evaluate_basis(
                draft.saving_basis,
                emission_service=self._emission_service,
                state=state,
            )
            if saving is None:
                steps.append(f"Dropped rec: {note}.")
                continue
            steps.append(note)
            kept.append((draft, saving))

        if not kept:
            return CoachEmpty(
                reason="Could not generate grounded recommendations from the data provided.",
                agent_reasoning=self._reasoning(
                    input_summary=input_summary,
                    steps=[*steps, "No recommendation survived validation."],
                    output_summary="No recommendations produced.",
                    start=start,
                ),
            )

        recommendations = [
            Recommendation(
                id=uuid4().hex,
                user_id=user_id,
                generated_at=moment,
                type=draft.type,
                title=draft.title,
                description=draft.description,
                expected_saving_kg=saving,
                difficulty=draft.difficulty,
                accepted=False,
                agent_reasoning=self._reasoning(
                    input_summary=input_summary,
                    steps=[
                        *steps,
                        f"Final {draft.type} ({draft.difficulty}) saving {saving} kg/wk.",
                    ],
                    output_summary=f"{draft.type} ({draft.difficulty}): {draft.title}",
                    start=start,
                ),
            )
            for draft, saving in kept
        ]
        self._log("coach.success", recommendation_count=len(recommendations))
        return CoachSuccess(recommendations=recommendations)

    def _reasoning(
        self,
        *,
        input_summary: str,
        steps: list[str],
        output_summary: str,
        start: int,
    ) -> AgentReasoning:
        """Build a Coach reasoning trace.

        Args:
            input_summary: One-line description of the input.
            steps: Ordered reasoning steps.
            output_summary: One-line description of the output.
            start: The ``_now_ms`` value captured at the start of the run.

        Returns:
            A populated :class:`AgentReasoning`.
        """
        return self._build_reasoning(
            agent_name="coach",
            input_summary=input_summary[:_INPUT_SUMMARY_LIMIT],
            steps=steps,
            output_summary=output_summary,
            latency_ms=self._now_ms() - start,
        )

    def _failed(
        self,
        reason: str,
        input_summary: str,
        steps: list[str],
        start: int,
    ) -> CoachFailed:
        """Assemble a :class:`CoachFailed` outcome with a reasoning trace.

        Args:
            reason: Human-readable failure explanation.
            input_summary: One-line description of the input.
            steps: Reasoning steps accumulated up to the failure.
            start: The ``_now_ms`` value captured at the start of the run.

        Returns:
            A populated :class:`CoachFailed`.
        """
        self._log("coach.failed", reason=reason)
        return CoachFailed(
            reason=reason,
            agent_reasoning=self._reasoning(
                input_summary=input_summary,
                steps=steps,
                output_summary=f"Failed: {reason}",
                start=start,
            ),
        )
