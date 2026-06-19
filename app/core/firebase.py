"""Lazy Firebase Admin SDK and Firestore client initialisation.

Both accessors are cached with :func:`functools.lru_cache` so the SDK is
initialised **at most once** per process, and only on first use — never at
import time.  This matters for testing (no live credentials needed to import
the module) and for Cloud Run cold starts (no blocking I/O during module load).

Usage::

    from app.core.firebase import get_firebase_app, get_firestore_async_client

    app = get_firebase_app()               # Firebase Admin SDK, for Auth etc.
    client = get_firestore_async_client()  # google-cloud-firestore AsyncClient
"""

from __future__ import annotations

from functools import lru_cache

import firebase_admin
from google.cloud.firestore import AsyncClient

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_firebase_app() -> firebase_admin.App:
    """Return the default Firebase Admin SDK app, initialising it on first call.

    Uses Application Default Credentials (ADC) — no explicit credential file
    is referenced in code.  On Cloud Run, ADC resolves to the attached service
    account automatically.  Locally, set ``GOOGLE_APPLICATION_CREDENTIALS`` to
    a service-account key file.

    Returns:
        The default :class:`firebase_admin.App` instance.
    """
    return firebase_admin.initialize_app()


@lru_cache(maxsize=1)
def get_firestore_async_client() -> AsyncClient:
    """Return a cached async Firestore client for the configured GCP project.

    The client is constructed from Application Default Credentials and scoped
    to ``settings.firebase_project_id``.  It is independent of the Firebase
    Admin SDK — use :func:`get_firebase_app` separately when Admin features
    (e.g. Auth token verification) are required.

    Returns:
        A :class:`google.cloud.firestore.AsyncClient` instance bound to the
        project declared in application settings.
    """
    settings = get_settings()
    return AsyncClient(project=settings.firebase_project_id)
