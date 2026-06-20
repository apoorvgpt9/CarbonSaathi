"""Async Firestore service for CarbonSaathi.

Wraps ``google-cloud-firestore`` ``AsyncClient`` in a typed service class.
All public methods are ``async``.  The service is instantiated once per
process via :func:`get_firestore_service` (backed by :func:`functools.lru_cache`).

Collection layout (from DECISIONS.md § 8)::

    users/{uid}
    users/{uid}/activities/{activity_id}
    users/{uid}/insights/{insight_id}
    users/{uid}/recommendations/{rec_id}

Pydantic → Firestore: ``model.model_dump(mode="json")``
Firestore → Pydantic: ``Model.model_validate(doc.to_dict())``
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import datetime
from functools import lru_cache
from typing import Any

import structlog
from google.cloud.firestore import AsyncClient, FieldFilter

from app.core.firebase import get_firestore_async_client
from app.models.activity import Activity
from app.models.generation_state import GenerationState
from app.models.insight import Insight
from app.models.recommendation import Recommendation
from app.models.user import UserProfile

_logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Fire-and-forget helper
# ---------------------------------------------------------------------------


def fire_and_forget[T](coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
    """Schedule a coroutine as a background task, swallowing exceptions safely.

    Wraps the coroutine in :func:`asyncio.create_task` and attaches a
    done-callback that logs any unhandled exception via structlog.  The caller
    is **not** notified of the error — use this only for non-critical writes
    (e.g. caching derived data) where a silent failure is acceptable.

    Args:
        coro: An awaitable coroutine to run in the background.

    Returns:
        The :class:`asyncio.Task` wrapping the coroutine.  The caller may
        await or cancel it, but is not required to.
    """
    task: asyncio.Task[T] = asyncio.create_task(coro)

    def _on_done(t: asyncio.Task[T]) -> None:
        if not t.cancelled():
            exc = t.exception()
            if exc is not None:
                _logger.error(
                    "fire_and_forget task raised an unhandled exception",
                    exc_info=exc,
                )

    task.add_done_callback(_on_done)
    return task


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class FirestoreService:
    """Typed async wrapper around the Firestore ``AsyncClient``.

    Accepts the client via constructor injection so that tests can pass a mock
    without touching module-level state.

    Attributes:
        _client: The underlying :class:`~google.cloud.firestore.AsyncClient`.
    """

    def __init__(self, client: AsyncClient) -> None:
        """Initialise the service with an async Firestore client.

        Args:
            client: A connected :class:`~google.cloud.firestore.AsyncClient`.
        """
        self._client = client

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def get_user(self, uid: str) -> UserProfile | None:
        """Fetch a user profile by UID.

        Args:
            uid: Firebase Authentication UID.

        Returns:
            The :class:`~app.models.user.UserProfile` if it exists, else
            ``None``.
        """
        doc_ref = self._client.collection("users").document(uid)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        data: dict[str, Any] = snapshot.to_dict() or {}
        return UserProfile.model_validate(data)

    async def upsert_user(self, profile: UserProfile) -> None:
        """Create or overwrite a user document in Firestore.

        Args:
            profile: The :class:`~app.models.user.UserProfile` to persist.

        Returns:
            None.
        """
        doc_ref = self._client.collection("users").document(profile.uid)
        await doc_ref.set(profile.model_dump(mode="json"))

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------

    async def add_activity(self, activity: Activity) -> str:
        """Persist an activity document, using ``activity.id`` as the doc ID.

        Args:
            activity: The :class:`~app.models.activity.Activity` to write.

        Returns:
            The Firestore document ID (equal to ``activity.id``).
        """
        doc_ref = (
            self._client.collection("users")
            .document(activity.user_id)
            .collection("activities")
            .document(activity.id)
        )
        await doc_ref.set(activity.model_dump(mode="json"))
        return activity.id

    async def list_activities(
        self,
        user_id: str,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[Activity]:
        """Return the most recent activities for a user.

        Args:
            user_id: Firebase UID of the target user.
            limit: Maximum number of activities to return (default 50).
            before: If provided, only activities with a timestamp strictly
                before this value are returned (cursor pagination).

        Returns:
            A list of :class:`~app.models.activity.Activity` objects ordered
            by timestamp descending, length ≤ ``limit``.
        """
        col_ref = self._client.collection("users").document(user_id).collection("activities")
        query = col_ref.order_by("timestamp", direction="DESCENDING").limit(limit)
        if before is not None:
            query = query.where(filter=FieldFilter("timestamp", "<", before))
        activities: list[Activity] = []
        async for doc in query.stream():
            data: dict[str, Any] = doc.to_dict() or {}
            if data:
                activities.append(Activity.model_validate(data))
        return activities

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    async def add_insight(self, insight: Insight) -> str:
        """Persist an insight document, using ``insight.id`` as the doc ID.

        Args:
            insight: The :class:`~app.models.insight.Insight` to write.

        Returns:
            The Firestore document ID (equal to ``insight.id``).
        """
        doc_ref = (
            self._client.collection("users")
            .document(insight.user_id)
            .collection("insights")
            .document(insight.id)
        )
        await doc_ref.set(insight.model_dump(mode="json"))
        return insight.id

    async def get_recent_insights(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[Insight]:
        """Return the most recently generated insights for a user.

        Args:
            user_id: Firebase UID of the target user.
            limit: Maximum number of insights to return (default 10).

        Returns:
            A list of :class:`~app.models.insight.Insight` objects ordered by
            ``generated_at`` descending, length ≤ ``limit``.
        """
        col_ref = self._client.collection("users").document(user_id).collection("insights")
        query = col_ref.order_by("generated_at", direction="DESCENDING").limit(limit)
        insights: list[Insight] = []
        async for doc in query.stream():
            data: dict[str, Any] = doc.to_dict() or {}
            if data:
                insights.append(Insight.model_validate(data))
        return insights

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    async def add_recommendation(self, rec: Recommendation) -> str:
        """Persist a recommendation document, using ``rec.id`` as the doc ID.

        Args:
            rec: The :class:`~app.models.recommendation.Recommendation` to write.

        Returns:
            The Firestore document ID (equal to ``rec.id``).
        """
        doc_ref = (
            self._client.collection("users")
            .document(rec.user_id)
            .collection("recommendations")
            .document(rec.id)
        )
        await doc_ref.set(rec.model_dump(mode="json"))
        return rec.id

    async def accept_recommendation(self, user_id: str, rec_id: str) -> bool:
        """Mark a recommendation as accepted.

        Performs a read-then-update (not a transaction); acceptable because
        concurrent ``accept`` races have no harmful outcome.

        Args:
            user_id: Firebase UID of the owning user.
            rec_id: ID of the recommendation to accept.

        Returns:
            ``True`` if the document existed and was updated; ``False`` if the
            document was not found.
        """
        doc_ref = (
            self._client.collection("users")
            .document(user_id)
            .collection("recommendations")
            .document(rec_id)
        )
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return False
        await doc_ref.update({"accepted": True})
        return True

    async def get_recent_recommendations(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[Recommendation]:
        """Return the most recently generated recommendations for a user.

        Args:
            user_id: Firebase UID of the target user.
            limit: Maximum number of recommendations to return (default 10).

        Returns:
            A list of :class:`~app.models.recommendation.Recommendation` objects
            ordered by ``generated_at`` descending, length <= ``limit``.
        """
        col_ref = self._client.collection("users").document(user_id).collection("recommendations")
        query = col_ref.order_by("generated_at", direction="DESCENDING").limit(limit)
        recommendations: list[Recommendation] = []
        async for doc in query.stream():
            data: dict[str, Any] = doc.to_dict() or {}
            if data:
                recommendations.append(Recommendation.model_validate(data))
        return recommendations

    async def get_activity(self, uid: str, activity_id: str) -> Activity | None:
        """Fetch a single activity by ID, scoped to the owning user.

        Returns ``None`` both when the document does not exist and when the
        stored ``user_id`` field does not match ``uid``, so that callers cannot
        distinguish between "not found" and "owned by another user".

        Args:
            uid: Firebase UID of the requesting user.
            activity_id: Firestore document ID of the activity.

        Returns:
            The :class:`~app.models.activity.Activity` if found and owned by
            ``uid``, else ``None``.
        """
        doc_ref = (
            self._client.collection("users")
            .document(uid)
            .collection("activities")
            .document(activity_id)
        )
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        data: dict[str, Any] = snapshot.to_dict() or {}
        if not data:
            return None
        activity = Activity.model_validate(data)
        if activity.user_id != uid:
            return None
        return activity

    async def list_activities_in_range(
        self,
        uid: str,
        start: datetime,
        end: datetime,
        limit: int = 200,
    ) -> list[Activity]:
        """Return activities whose timestamp falls in [start, end).

        Ordered by timestamp descending.  Used primarily by the dashboard to
        aggregate emissions over a rolling 7-day IST window.

        Args:
            uid: Firebase UID of the target user.
            start: Inclusive lower bound (UTC, timezone-aware).
            end: Exclusive upper bound (UTC, timezone-aware).
            limit: Maximum number of activities to return (default 200).

        Returns:
            A list of :class:`~app.models.activity.Activity` objects ordered
            by timestamp descending, length ≤ ``limit``.
        """
        col_ref = self._client.collection("users").document(uid).collection("activities")
        query = (
            col_ref.order_by("timestamp", direction="DESCENDING")
            .where(filter=FieldFilter("timestamp", ">=", start))
            .where(filter=FieldFilter("timestamp", "<", end))
            .limit(limit)
        )
        activities: list[Activity] = []
        async for doc in query.stream():
            data: dict[str, Any] = doc.to_dict() or {}
            if data:
                activities.append(Activity.model_validate(data))
        return activities

    # ------------------------------------------------------------------
    # Generation state
    # ------------------------------------------------------------------

    async def get_generation_state(self, uid: str) -> GenerationState | None:
        """Fetch the insight-pipeline generation-state document for a user.

        Args:
            uid: Firebase UID of the target user.

        Returns:
            The :class:`~app.models.generation_state.GenerationState` if a prior
            run has been recorded, else ``None``.
        """
        doc_ref = (
            self._client.collection("users")
            .document(uid)
            .collection("state")
            .document("generation")
        )
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        data: dict[str, Any] = snapshot.to_dict() or {}
        if not data:
            return None
        return GenerationState.model_validate(data)

    async def set_generation_state(self, uid: str, state: GenerationState) -> None:
        """Create or overwrite the generation-state document for a user.

        Args:
            uid: Firebase UID of the owning user.
            state: The :class:`~app.models.generation_state.GenerationState` to
                persist (idempotent ``set``).

        Returns:
            None.
        """
        doc_ref = (
            self._client.collection("users")
            .document(uid)
            .collection("state")
            .document("generation")
        )
        await doc_ref.set(state.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Module-level cached accessor
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_firestore_service() -> FirestoreService:
    """Return the singleton :class:`FirestoreService` for the application.

    Constructs the service once using the cached async Firestore client from
    :func:`~app.core.firebase.get_firestore_async_client`.

    Returns:
        The application-wide :class:`FirestoreService` instance.
    """
    return FirestoreService(client=get_firestore_async_client())
