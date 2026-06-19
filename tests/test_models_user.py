"""Tests for app/models/user.py — IndianState, HomeProfile, UserProfile."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.user import HomeProfile, IndianState, UserProfile


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _valid_home() -> dict[str, object]:
    return {
        "bhk": 2,
        "has_ac": True,
        "fridge_class": "3-star",
        "dietary": "veg",
    }


def _valid_profile(**overrides: object) -> dict[str, object]:
    now = _utc_now()
    base: dict[str, object] = {
        "uid": "user-123",
        "email": "test@example.com",
        "display_name": "Test User",
        "state": IndianState.KARNATAKA,
        "home_profile": HomeProfile(**_valid_home()),
        "created_at": now,
        "last_active": now,
    }
    base.update(overrides)
    return base


def test_user_profile_valid() -> None:
    p = UserProfile(**_valid_profile())
    assert p.uid == "user-123"
    assert p.state == IndianState.KARNATAKA
    assert p.onboarding_complete is False


def test_home_profile_bhk_zero_rejected() -> None:
    data = _valid_home()
    data["bhk"] = 0
    with pytest.raises(ValidationError):
        HomeProfile(**data)


def test_home_profile_bhk_six_rejected() -> None:
    data = _valid_home()
    data["bhk"] = 6
    with pytest.raises(ValidationError):
        HomeProfile(**data)


def test_user_profile_invalid_state() -> None:
    with pytest.raises(ValidationError):
        UserProfile(**_valid_profile(state="Wakanda"))


def test_user_profile_naive_created_at_rejected() -> None:
    with pytest.raises(ValidationError):
        UserProfile(
            **_valid_profile(created_at=datetime(2025, 1, 1))  # naive
        )


def test_user_profile_naive_last_active_rejected() -> None:
    with pytest.raises(ValidationError):
        UserProfile(
            **_valid_profile(last_active=datetime(2025, 1, 1))  # naive
        )


def test_user_profile_is_frozen() -> None:
    p = UserProfile(**_valid_profile())
    with pytest.raises((AttributeError, ValidationError)):
        p.uid = "other"  # type: ignore[misc]


def test_home_profile_invalid_dietary() -> None:
    data = _valid_home()
    data["dietary"] = "carnivore"
    with pytest.raises(ValidationError):
        HomeProfile(**data)


def test_home_profile_invalid_fridge_class() -> None:
    data = _valid_home()
    data["fridge_class"] = "6-star"
    with pytest.raises(ValidationError):
        HomeProfile(**data)


def test_user_profile_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        UserProfile(**_valid_profile(surprise="field"))


def test_user_profile_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserProfile(**_valid_profile(email="not-an-email"))


def test_indian_state_enum_values() -> None:
    assert IndianState.KARNATAKA.value == "Karnataka"
    assert IndianState.DELHI.value == "Delhi"
    assert IndianState.DADRA_AND_NAGAR_HAVELI.value == ("Dadra and Nagar Haveli and Daman and Diu")
    # All 36 members present
    assert len(IndianState) == 36
