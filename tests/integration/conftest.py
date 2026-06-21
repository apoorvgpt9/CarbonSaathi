"""Fixtures for emulator-backed integration tests.

The Firestore emulator is started externally (via ``make test-emulator`` or
``gcloud emulators firestore start --host-port=localhost:8090``).  Tests in
this package auto-skip when the emulator is not reachable, so the default
``pytest`` / ``make test`` invocation stays fast and clean.

Emulator choice: ``gcloud emulators firestore start --host-port=localhost:8090``
uses port 8090 (not 8080) to avoid collision with the CarbonSaathi dev server.
No extra packages are needed; ``google-cloud-firestore>=2.17.0`` (already in
production deps) connects to the emulator automatically when
``FIRESTORE_EMULATOR_HOST`` is set.
"""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncGenerator

import pytest
from google.cloud.firestore import AsyncClient

from app.services.firestore_service import FirestoreService

_EMULATOR_HOST = "localhost"
_EMULATOR_PORT = 8090
_EMULATOR_HOST_PORT = f"{_EMULATOR_HOST}:{_EMULATOR_PORT}"
_EMULATOR_PROJECT = "test-emulator-project"


def _emulator_reachable() -> bool:
    """Return ``True`` when the Firestore emulator is accepting TCP connections.

    Returns:
        ``True`` if a connection to the emulator host/port succeeds within
        one second, ``False`` otherwise.
    """
    try:
        with socket.create_connection((_EMULATOR_HOST, _EMULATOR_PORT), timeout=1.0):
            return True
    except OSError:
        return False


@pytest.fixture
async def firestore_emulator_client() -> AsyncGenerator[AsyncClient]:
    """Yield a real Firestore ``AsyncClient`` connected to the local emulator.

    Skips the test immediately if the emulator is not running on
    ``localhost:8090``.  Sets ``FIRESTORE_EMULATOR_HOST`` for the duration of
    the test so the SDK routes all traffic to the emulator rather than GCP.
    Data is NOT automatically cleared between tests — callers must use
    unique user IDs (e.g. ``str(uuid4())``) to avoid cross-test pollution.

    To start the emulator manually::

        gcloud emulators firestore start --host-port=localhost:8090

    Or use the project Makefile target::

        make test-emulator

    Yields:
        A connected :class:`~google.cloud.firestore.AsyncClient` bound to the
        emulator.
    """
    if not _emulator_reachable():
        pytest.skip(
            f"Firestore emulator not running on {_EMULATOR_HOST_PORT} — "
            "run 'make test-emulator' to start the emulator and execute these tests."
        )

    old_val = os.environ.get("FIRESTORE_EMULATOR_HOST")
    os.environ["FIRESTORE_EMULATOR_HOST"] = _EMULATOR_HOST_PORT
    client: AsyncClient = AsyncClient(project=_EMULATOR_PROJECT)
    try:
        yield client
    finally:
        await client.close()  # type: ignore[no-untyped-call]
        if old_val is None:
            os.environ.pop("FIRESTORE_EMULATOR_HOST", None)
        else:
            os.environ["FIRESTORE_EMULATOR_HOST"] = old_val


@pytest.fixture
async def real_firestore_service(
    firestore_emulator_client: AsyncClient,
) -> FirestoreService:
    """Return a :class:`FirestoreService` backed by the local Firestore emulator.

    Depends on :func:`firestore_emulator_client`, which auto-skips when the
    emulator is not running.

    Args:
        firestore_emulator_client: A connected emulator ``AsyncClient``.

    Returns:
        A :class:`~app.services.firestore_service.FirestoreService` instance
        using the emulator as its storage backend.
    """
    return FirestoreService(client=firestore_emulator_client)
