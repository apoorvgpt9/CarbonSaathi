"""Logger agent prompt template (v1) and Gemini function declarations.

Defines the system instruction and the three function-calling schemas
(``log_transport``, ``log_electricity``, ``log_food``) used by the Logger.
The ``mode`` and ``category`` enums are sourced from the
:class:`~app.services.emission_service.EmissionService` at import time so the
function schemas can never drift from the underlying emission-factor data.
"""

from __future__ import annotations

from google.generativeai.protos import FunctionDeclaration, Schema, Type

from app.services.emission_service import get_emission_service

PROMPT_VERSION = "logger-v1"
"""Version identifier for the Logger prompt template."""

_emission_service = get_emission_service()
_TRANSPORT_MODES: list[str] = _emission_service.list_transport_modes()
_FOOD_CATEGORIES: list[str] = _emission_service.list_food_categories()

SYSTEM_INSTRUCTION = """\
You are the CarbonSaathi Logger, a tool for Indian metro professionals. Read one
short message describing a single everyday activity and record it by calling
exactly one function:

- log_transport: a trip or commute (auto-rickshaw, metro, bus, taxi/cab/Uber/Ola,
  two-wheeler, four-wheeler, walking, or work-from-home).
- log_electricity: household power use (units/kWh, an appliance, or a monthly
  bill in rupees).
- log_food: a meal or food item (veg thali, dal, rice, paneer, chicken, mutton,
  fish, egg, dairy, or a snack).

Rules:
- Call exactly one function: the activity the user most clearly described.
- Use the provided enum values for mode and category. Pick the closest Indian
  match: Uber/Ola/cab -> taxi, auto -> auto_rickshaw_cng, paneer ->
  paneer_serving_100g, thali/veg meal -> veg_meal.
- Never invent precise numbers. If distance, quantity, or servings are unstated,
  estimate a reasonable Indian urban default and record the uncertainty in notes.
- For electricity, prefer kWh when stated; otherwise pass the bill amount as
  bill_amount_inr.
- Do not answer questions, give advice, or add commentary: only call a function.
"""
"""System instruction supplied to the Gemini Flash Logger model."""

_log_transport = FunctionDeclaration(
    name="log_transport",
    description="Record one transport or commute leg the user described.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "mode": Schema(
                type=Type.STRING,
                enum=_TRANSPORT_MODES,
                description="Transport mode key; choose the closest match.",
            ),
            "km": Schema(
                type=Type.NUMBER,
                description="Distance in kilometres; estimate if unstated.",
            ),
            "notes": Schema(
                type=Type.STRING,
                description="Optional caveats or uncertainty; omit if none.",
            ),
        },
        required=["mode", "km"],
    ),
)

_log_electricity = FunctionDeclaration(
    name="log_electricity",
    description="Record one household electricity usage the user described.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "kwh": Schema(
                type=Type.NUMBER,
                description="Energy in kWh / units, if stated.",
            ),
            "appliance": Schema(
                type=Type.STRING,
                description="Appliance involved, if named.",
            ),
            "hours": Schema(
                type=Type.NUMBER,
                description="Hours of operation, if stated.",
            ),
            "bill_amount_inr": Schema(
                type=Type.NUMBER,
                description="Monthly bill amount in rupees, if given instead of kWh.",
            ),
        },
        required=[],
    ),
)

_log_food = FunctionDeclaration(
    name="log_food",
    description="Record one meal or food item the user described.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "category": Schema(
                type=Type.STRING,
                enum=_FOOD_CATEGORIES,
                description="Food category key; choose the closest match.",
            ),
            "servings": Schema(
                type=Type.NUMBER,
                description="Number of servings consumed (greater than zero).",
            ),
        },
        required=["category", "servings"],
    ),
)

FUNCTION_DECLARATIONS: list[FunctionDeclaration] = [
    _log_transport,
    _log_electricity,
    _log_food,
]
"""The three function declarations passed to the Gemini model as tools."""
