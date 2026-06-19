"""Tests for app/core/gemini.py — lazy GenerativeModelFactory and singleton."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from app.core.gemini import GenerativeModelFactory, get_gemini_client


@pytest.fixture(autouse=True)
def _clear_gemini_cache() -> Iterator[None]:
    """Reset the lru_cache around get_gemini_client before and after each test."""
    get_gemini_client.cache_clear()
    yield
    get_gemini_client.cache_clear()


def test_configure_is_lazy_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_configure = MagicMock()
    monkeypatch.setattr("google.generativeai.configure", fake_configure)
    monkeypatch.setattr("google.generativeai.GenerativeModel", MagicMock())

    # Not configured merely by importing / clearing the cache.
    fake_configure.assert_not_called()

    factory1 = get_gemini_client()
    assert isinstance(factory1, GenerativeModelFactory)
    fake_configure.assert_called_once()

    factory2 = get_gemini_client()
    assert factory2 is factory1
    fake_configure.assert_called_once()  # lru_cache prevents a second configure


def test_flash_builds_flash_model(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = MagicMock()
    fake_model_cls = MagicMock(return_value=fake_model)
    monkeypatch.setattr("google.generativeai.configure", MagicMock())
    monkeypatch.setattr("google.generativeai.GenerativeModel", fake_model_cls)

    factory = get_gemini_client()
    tools = [object()]
    result = factory.flash(system_instruction="sys", tools=tools)

    assert result is fake_model
    _, kwargs = fake_model_cls.call_args
    assert kwargs["model_name"] == "gemini-2.5-flash"
    assert kwargs["system_instruction"] == "sys"
    assert kwargs["tools"] is tools


def test_pro_builds_pro_model(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = MagicMock()
    fake_model_cls = MagicMock(return_value=fake_model)
    monkeypatch.setattr("google.generativeai.configure", MagicMock())
    monkeypatch.setattr("google.generativeai.GenerativeModel", fake_model_cls)

    factory = get_gemini_client()
    result = factory.pro()

    assert result is fake_model
    _, kwargs = fake_model_cls.call_args
    assert kwargs["model_name"] == "gemini-2.5-pro"
    assert kwargs["system_instruction"] is None
    assert kwargs["tools"] is None
