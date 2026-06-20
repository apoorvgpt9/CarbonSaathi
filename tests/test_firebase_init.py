"""Tests for app/core/firebase.py — lazy init, lru_cache behaviour."""

from __future__ import annotations

import importlib
import sys
from typing import Any
from unittest.mock import MagicMock, patch


def _reload_firebase_module() -> Any:
    """Force a fresh import of app.core.firebase, bypassing sys.modules cache."""
    sys.modules.pop("app.core.firebase", None)
    return importlib.import_module("app.core.firebase")


def test_initialize_app_not_called_at_import() -> None:
    """Importing the module must not trigger firebase_admin.initialize_app."""
    with patch("firebase_admin.initialize_app") as mock_init:
        _reload_firebase_module()
        mock_init.assert_not_called()


def test_get_firebase_app_calls_initialize_app_once() -> None:
    """get_firebase_app() must call initialize_app exactly once."""
    fb: Any = _reload_firebase_module()
    with patch("firebase_admin.initialize_app", return_value=MagicMock()) as mock_init:
        fb.get_firebase_app.cache_clear()
        fb.get_firebase_app()
        mock_init.assert_called_once()


def test_get_firebase_app_lru_cache_prevents_second_call() -> None:
    """Calling get_firebase_app() twice must invoke initialize_app only once."""
    fb: Any = _reload_firebase_module()
    with patch("firebase_admin.initialize_app", return_value=MagicMock()) as mock_init:
        fb.get_firebase_app.cache_clear()
        fb.get_firebase_app()
        fb.get_firebase_app()
        assert mock_init.call_count == 1


def test_get_firebase_app_cache_clear_allows_reinit() -> None:
    """After cache_clear(), get_firebase_app() calls initialize_app again."""
    fb: Any = _reload_firebase_module()
    with patch("firebase_admin.initialize_app", return_value=MagicMock()) as mock_init:
        fb.get_firebase_app.cache_clear()
        fb.get_firebase_app()
        fb.get_firebase_app.cache_clear()
        fb.get_firebase_app()
        assert mock_init.call_count == 2


def test_get_firestore_async_client_is_cached() -> None:
    """Calling get_firestore_async_client() twice returns the same object."""
    fb: Any = _reload_firebase_module()
    mock_client = MagicMock()
    # Patch the name as bound inside the firebase module (it does
    # ``from google.cloud.firestore import AsyncClient``), so no real client is
    # constructed and no Application Default Credentials are required.
    with patch("app.core.firebase.AsyncClient", return_value=mock_client):
        fb.get_firestore_async_client.cache_clear()
        c1 = fb.get_firestore_async_client()
        c2 = fb.get_firestore_async_client()
        assert c1 is c2
