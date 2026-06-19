"""Input governance layer for CarbonSaathi.

Provides :func:`check_input`, a synchronous, pure-Python gate that classifies
user-supplied text before it reaches any LLM.  It is intentionally conservative
— false positives are preferred over passing harmful input downstream.

**Limitations (by design — defense-in-depth only):**

* Not multilingual — patterns are English-only; Hindi / transliterated abuse or
  injection attempts are not detected.
* Not encoding-resistant — Base64, ROT13, or Unicode-obfuscated payloads bypass
  all checks.
* Allowlist is shallow — domain keyword matching cannot distinguish a genuine
  carbon activity from a contrived sentence containing those words.
* Regex injection patterns cover known prompt-injection idioms only; novel
  phrasing will pass through.
* The abuse word list is minimal; extend it in production with a dedicated
  content-moderation API.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Compiled injection patterns
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore (all |the )?(previous|prior|above)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"disregard (all |the )?(previous|prior|above)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"system prompt", re.IGNORECASE | re.MULTILINE),
    re.compile(r"you are (now )?(a )?(different|new)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"act as (a )?(?!.*carbon)", re.IGNORECASE | re.MULTILINE | re.DOTALL),
    re.compile(r"reveal (your )?instructions", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bsudo\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"</?(?:system|user|assistant)>", re.IGNORECASE | re.MULTILINE),
    re.compile(r"forget (everything|all|your)", re.IGNORECASE | re.MULTILINE),
)

# ---------------------------------------------------------------------------
# Carbon-domain allowlist (substring match, lower-cased input)
# ---------------------------------------------------------------------------

_CARBON_KEYWORDS: frozenset[str] = frozenset(
    {
        # Transport
        "cab",
        "uber",
        "ola",
        "rapido",
        "metro",
        "bus",
        "auto",
        "rickshaw",
        "walk",
        "cycle",
        "bicycle",
        "bike",
        "scooter",
        "car",
        "drive",
        "drove",
        "train",
        "flight",
        "fly",
        "flew",
        "ferry",
        "commute",
        "commuted",
        "travel",
        "travelled",
        "fuel",
        "petrol",
        "diesel",
        "cng",
        "ev",
        "two-wheeler",
        "four-wheeler",
        # WFH / office
        "wfh",
        "work from home",
        "work-from-home",
        "office",
        "remote",
        # Electricity
        "electricity",
        "electric",
        "kwh",
        "unit",
        "bill",
        "power",
        "ac",
        "air conditioner",
        "fan",
        "fridge",
        "refrigerator",
        "washing machine",
        "geyser",
        "heater",
        "microwave",
        "solar",
        "inverter",
        # Food
        "meal",
        "breakfast",
        "lunch",
        "dinner",
        "snack",
        "eat",
        "ate",
        "food",
        "paneer",
        "chicken",
        "mutton",
        "fish",
        "egg",
        "dal",
        "rice",
        "roti",
        "dairy",
        "milk",
        "meat",
        "vegetarian",
        "veg",
        "non-veg",
        "eggetarian",
        "cook",
        "cooked",
        "restaurant",
        "ordered",
        # Emissions / carbon
        "carbon",
        "co2",
        "emission",
        "footprint",
        "greenhouse",
        "climate",
        "offset",
        "reduce",
        "green",
        "eco",
    }
)

# ---------------------------------------------------------------------------
# Abuse word list  (short, English-only)
# ---------------------------------------------------------------------------

_ABUSE_WORDS: frozenset[str] = frozenset({"fuck", "fucking", "shit", "bitch", "bastard", "asshole", "cunt"})

# ---------------------------------------------------------------------------
# Off-topic character threshold
# ---------------------------------------------------------------------------

_OFF_TOPIC_MIN_LEN = 20


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class GovernanceResult(BaseModel):
    """Outcome of an input governance check.

    Attributes:
        allowed: ``True`` when the input is safe to forward to an LLM.
        reason: Human-readable explanation when ``allowed`` is ``False``;
            ``None`` when the input is clean.
        category: Machine-readable classification used for metrics and logging.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    reason: str | None
    category: Literal["ok", "off_topic", "injection", "abuse", "empty"] = "ok"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_input(text: str) -> GovernanceResult:
    """Classify user input before it reaches any LLM.

    Checks are evaluated in strict precedence order — **first match wins**:

    1. ``empty``    — blank or whitespace-only text.
    2. ``injection`` — matches a known prompt-injection regex pattern.
    3. ``abuse``    — contains a word from the profanity blocklist.
    4. ``off_topic`` — longer than :data:`_OFF_TOPIC_MIN_LEN` characters with
       zero carbon-domain keyword hits.
    5. ``ok``       — all checks passed; safe to forward.

    Args:
        text: Raw user-submitted string.  Must not be pre-processed by the
            caller — normalisations (strip, lower) are applied internally.

    Returns:
        A :class:`GovernanceResult` with ``allowed=True`` for category ``ok``
        and ``allowed=False`` for all other categories.

    Note:
        See module-level docstring for known limitations.
    """
    # 1. Empty / whitespace
    if not text or not text.strip():
        return GovernanceResult(allowed=False, reason="Input is empty.", category="empty")

    # 2. Injection
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return GovernanceResult(
                allowed=False,
                reason="Input contains a potential prompt-injection pattern.",
                category="injection",
            )

    # 3. Abuse
    lower = text.lower()
    for word in _ABUSE_WORDS:
        # Use word-boundary-aware check to avoid false positives on substrings
        if re.search(rf"\b{re.escape(word)}\b", lower):
            return GovernanceResult(
                allowed=False,
                reason="Input contains inappropriate language.",
                category="abuse",
            )

    # 4. Off-topic — only triggered for longer inputs to allow short greetings
    if len(text.strip()) > _OFF_TOPIC_MIN_LEN:
        if not any(kw in lower for kw in _CARBON_KEYWORDS):
            return GovernanceResult(
                allowed=False,
                reason="Input does not appear to be related to carbon footprint tracking.",
                category="off_topic",
            )

    # 5. OK
    return GovernanceResult(allowed=True, reason=None, category="ok")
