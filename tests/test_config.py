"""Tests for application configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_loads_from_env() -> None:
    settings = get_settings()
    assert settings.firebase_project_id == "test-project"
    assert settings.firebase_api_key == "test-fb-api-key"
    assert settings.firebase_auth_domain == "test.firebaseapp.com"
    assert settings.firebase_app_id == "1:test:web:test"
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"


def test_allowed_origins_parsed_from_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://a.com, http://b.com")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.allowed_origins == ["http://a.com", "http://b.com"]


def test_allowed_origins_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.allowed_origins == [
        "http://localhost:8080",
        "https://carbonsaathi-ahkpdce5pa-el.a.run.app",
    ]


def test_allowed_origins_accepts_list() -> None:
    settings = Settings(allowed_origins=["http://x.com", "http://y.com"])
    assert settings.allowed_origins == ["http://x.com", "http://y.com"]


def test_rate_limit_default_is_30() -> None:
    assert get_settings().rate_limit_per_minute == 30


def test_log_level_is_uppercased(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    get_settings.cache_clear()
    assert get_settings().log_level == "DEBUG"


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "NOPE")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_invalid_app_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "qa")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_rate_limit_out_of_range_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_gemini_api_key_is_secret() -> None:
    settings = get_settings()
    assert str(settings.gemini_api_key) == "**********"
    assert settings.gemini_api_key.get_secret_value() == "test-gemini-key"


def test_unknown_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]  # exercise extra="forbid"
            _env_file=None,
            gemini_api_key="k",
            firebase_project_id="p",
            firebase_api_key="a",
            firebase_auth_domain="d",
            firebase_app_id="e",
            definitely_not_a_field="x",
        )


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
