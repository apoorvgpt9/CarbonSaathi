"""Tests for app/core/auth.py — the verify_firebase_token dependency.

Every test calls :func:`~app.core.auth.verify_firebase_token` directly and
patches ``firebase_admin.auth.verify_id_token`` and
``app.core.auth.get_firebase_app`` so no real Firebase initialisation or network
access occurs.  Structured log events are asserted via
``structlog.testing.capture_logs``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from firebase_admin import auth as firebase_auth
from structlog.testing import capture_logs

from app.core.auth import CurrentUser, verify_firebase_token

_DECODED: dict[str, Any] = {
    "uid": "uid-1",
    "email": "riya@example.com",
    "email_verified": True,
    "name": "Riya",
}


def _mock_request() -> MagicMock:
    """Return a mock request with a writable ``state`` namespace.

    ``verify_firebase_token`` sets ``request.state.user`` on success, so the
    mock must accept attribute assignment on ``state``.
    """
    request = MagicMock()
    request.state = SimpleNamespace()
    return request


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_success_returns_current_user(mock_verify: MagicMock, _mock_app: MagicMock) -> None:
    mock_verify.return_value = dict(_DECODED)
    user = await verify_firebase_token(_mock_request(), authorization="Bearer good-token")
    assert user == CurrentUser(
        uid="uid-1", email="riya@example.com", email_verified=True, name="Riya"
    )
    assert mock_verify.call_args.args[0] == "good-token"


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_success_minimal_claims_defaults(
    mock_verify: MagicMock, _mock_app: MagicMock
) -> None:
    mock_verify.return_value = {"uid": "uid-2"}
    user = await verify_firebase_token(_mock_request(), authorization="Bearer tok")
    assert user == CurrentUser(uid="uid-2")
    assert user.email is None
    assert user.email_verified is False
    assert user.name is None


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_bearer_prefix_case_insensitive(mock_verify: MagicMock, _mock_app: MagicMock) -> None:
    mock_verify.return_value = dict(_DECODED)
    user = await verify_firebase_token(_mock_request(), authorization="bEaReR tok")
    assert user.uid == "uid-1"
    assert mock_verify.call_args.args[0] == "tok"


async def test_missing_header_401() -> None:
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization=None)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication failed"
    assert any(entry["event"] == "auth.malformed_header" for entry in logs)


async def test_missing_bearer_prefix_401() -> None:
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization="token-without-scheme")
    assert exc.value.status_code == 401
    assert any(entry["event"] == "auth.malformed_header" for entry in logs)


async def test_empty_token_after_bearer_401() -> None:
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization="Bearer    ")
    assert exc.value.status_code == 401
    assert any(
        entry["event"] == "auth.malformed_header" and entry["log_level"] == "warning"
        for entry in logs
    )


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_invalid_id_token_401(mock_verify: MagicMock, _mock_app: MagicMock) -> None:
    mock_verify.side_effect = firebase_auth.InvalidIdTokenError("bad token")
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization="Bearer x")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication failed"
    assert any(
        entry["event"] == "auth.invalid_token" and entry["log_level"] == "warning" for entry in logs
    )


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_expired_token_401(mock_verify: MagicMock, _mock_app: MagicMock) -> None:
    mock_verify.side_effect = firebase_auth.ExpiredIdTokenError("expired", cause=None)
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization="Bearer x")
    assert exc.value.status_code == 401
    assert any(entry["event"] == "auth.expired_token" for entry in logs)


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_revoked_token_401(mock_verify: MagicMock, _mock_app: MagicMock) -> None:
    mock_verify.side_effect = firebase_auth.RevokedIdTokenError("revoked")
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization="Bearer x")
    assert exc.value.status_code == 401
    assert any(entry["event"] == "auth.revoked_token" for entry in logs)


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_cert_fetch_failed_401(mock_verify: MagicMock, _mock_app: MagicMock) -> None:
    mock_verify.side_effect = firebase_auth.CertificateFetchError("cert fail", cause=None)
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization="Bearer x")
    assert exc.value.status_code == 401
    assert any(entry["event"] == "auth.cert_fetch_failed" for entry in logs)


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_value_error_401(mock_verify: MagicMock, _mock_app: MagicMock) -> None:
    mock_verify.side_effect = ValueError("not a string")
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization="Bearer x")
    assert exc.value.status_code == 401
    assert any(entry["event"] == "auth.value_error" for entry in logs)


@patch("app.core.auth.get_firebase_app", return_value=MagicMock())
@patch.object(firebase_auth, "verify_id_token")
async def test_unexpected_exception_401_logs_error(
    mock_verify: MagicMock, _mock_app: MagicMock
) -> None:
    mock_verify.side_effect = RuntimeError("boom")
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await verify_firebase_token(_mock_request(), authorization="Bearer x")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication failed"
    assert any(
        entry["event"] == "auth.unexpected_error" and entry["log_level"] == "error"
        for entry in logs
    )
