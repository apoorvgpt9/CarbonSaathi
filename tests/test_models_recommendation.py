"""Tests for app/models/recommendation.py — Recommendation, RecType, Difficulty."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.recommendation import Recommendation


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _valid_rec(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "rec-001",
        "user_id": "user-123",
        "generated_at": _utc_now(),
        "type": "swap",
        "title": "Switch from cab to metro for your daily commute",
        "description": (
            "Your Bangalore commute route has excellent metro coverage. "
            "Switching from cab to metro could save ~1.2 kg CO₂e per day."
        ),
        "expected_saving_kg": 1.2,
        "difficulty": "easy",
    }
    base.update(overrides)
    return base


def test_recommendation_valid() -> None:
    r = Recommendation(**_valid_rec())
    assert r.id == "rec-001"
    assert r.type == "swap"
    assert r.accepted is False
    assert r.agent_reasoning is None


def test_recommendation_accepted_default_false() -> None:
    r = Recommendation(**_valid_rec())
    assert r.accepted is False


def test_recommendation_negative_expected_saving_rejected() -> None:
    with pytest.raises(ValidationError):
        Recommendation(**_valid_rec(expected_saving_kg=-0.5))


def test_recommendation_zero_expected_saving_ok() -> None:
    r = Recommendation(**_valid_rec(expected_saving_kg=0.0))
    assert r.expected_saving_kg == 0.0


def test_recommendation_invalid_difficulty_rejected() -> None:
    with pytest.raises(ValidationError):
        Recommendation(**_valid_rec(difficulty="trivial"))


def test_recommendation_invalid_type_rejected() -> None:
    with pytest.raises(ValidationError):
        Recommendation(**_valid_rec(type="invest"))


def test_recommendation_agent_reasoning_optional() -> None:
    r = Recommendation(**_valid_rec(agent_reasoning=None))
    assert r.agent_reasoning is None


def test_recommendation_is_frozen() -> None:
    r = Recommendation(**_valid_rec())
    with pytest.raises((AttributeError, ValidationError)):
        r.accepted = True  # type: ignore[misc]


def test_recommendation_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Recommendation(**_valid_rec(unexpected="field"))
