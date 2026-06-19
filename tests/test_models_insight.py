"""Tests for app/models/insight.py — Insight, InsightType."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.insight import Insight


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _valid_insight(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "ins-001",
        "user_id": "user-123",
        "generated_at": _utc_now(),
        "type": "trend",
        "title": "Your transport emissions dropped 20% this week",
        "description": (
            "You used the metro four times and walked twice, which is significantly "
            "better than last week when you took a cab every day."
        ),
        "supporting_activity_ids": ["act-001", "act-002"],
    }
    base.update(overrides)
    return base


def test_insight_valid() -> None:
    i = Insight(**_valid_insight())
    assert i.id == "ins-001"
    assert i.type == "trend"
    assert i.agent_reasoning is None


def test_insight_title_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        Insight(**_valid_insight(title=""))


def test_insight_title_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        Insight(**_valid_insight(title="t" * 201))


def test_insight_title_max_length_ok() -> None:
    i = Insight(**_valid_insight(title="t" * 200))
    assert len(i.title) == 200


def test_insight_description_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        Insight(**_valid_insight(description="d" * 2001))


def test_insight_invalid_type_rejected() -> None:
    with pytest.raises(ValidationError):
        Insight(**_valid_insight(type="summary"))


def test_insight_agent_reasoning_optional() -> None:
    i = Insight(**_valid_insight(agent_reasoning=None))
    assert i.agent_reasoning is None


def test_insight_supporting_ids_empty_list_ok() -> None:
    i = Insight(**_valid_insight(supporting_activity_ids=[]))
    assert i.supporting_activity_ids == []


def test_insight_is_frozen() -> None:
    i = Insight(**_valid_insight())
    with pytest.raises((AttributeError, ValidationError)):
        i.title = "Changed"  # type: ignore[misc]
