"""Tests for app/services/firestore_service.py — FirestoreService, fire_and_forget."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.activity import Activity
from app.models.insight import Insight
from app.models.recommendation import Recommendation
from app.models.user import HomeProfile, IndianState, UserProfile
from app.services.firestore_service import FirestoreService, fire_and_forget, get_firestore_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _home() -> HomeProfile:
    return HomeProfile(bhk=2, has_ac=True, fridge_class="3-star", dietary="veg")


def _user(uid: str = "u1") -> UserProfile:
    now = _utc_now()
    return UserProfile(
        uid=uid,
        email="test@example.com",
        display_name="Test",
        state=IndianState.KARNATAKA,
        home_profile=_home(),
        created_at=now,
        last_active=now,
    )


def _activity(aid: str = "a1", uid: str = "u1") -> Activity:
    return Activity(
        id=aid,
        user_id=uid,
        type="transport",
        timestamp=_utc_now(),
        raw_input="Took metro to work",
        structured_data={"mode": "metro"},
        emission_kg_co2e=0.05,
        confidence="high",
        emission_factor_source="DMRC 2023",
    )


def _insight(iid: str = "i1", uid: str = "u1") -> Insight:
    return Insight(
        id=iid,
        user_id=uid,
        generated_at=_utc_now(),
        type="trend",
        title="Great week",
        description="Your emissions dropped 15% vs last week.",
        supporting_activity_ids=["a1"],
    )


def _rec(rid: str = "r1", uid: str = "u1") -> Recommendation:
    return Recommendation(
        id=rid,
        user_id=uid,
        generated_at=_utc_now(),
        type="swap",
        title="Use metro",
        description="Switch to metro for your daily commute.",
        expected_saving_kg=1.0,
        difficulty="easy",
    )


def _empty_async_gen(*_args: object, **_kwargs: object) -> AsyncGenerator[Any]:
    """Async generator that yields nothing."""

    async def _gen() -> AsyncGenerator[Any]:
        return
        yield  # makes it an async generator

    return _gen()


def _make_client(
    *,
    snapshot_exists: bool = False,
    snapshot_data: dict[str, object] | None = None,
) -> MagicMock:
    """Build a simple MagicMock Firestore client.

    Uses ``return_value`` chains (no ``side_effect``) so individual tests can
    override specific links in the chain via standard ``mock.x.return_value =
    …`` assignments.

    The default snapshot models a "not found" document (``exists=False``).
    """
    snapshot = MagicMock()
    snapshot.exists = snapshot_exists
    snapshot.to_dict.return_value = snapshot_data or {}

    doc_ref = MagicMock()
    doc_ref.get = AsyncMock(return_value=snapshot)
    doc_ref.set = AsyncMock(return_value=None)
    doc_ref.update = AsyncMock(return_value=None)

    # sub-collection (e.g. users/{uid}/activities)
    sub_col = MagicMock()
    sub_col.document.return_value = doc_ref
    sub_col.order_by.return_value = sub_col
    sub_col.limit.return_value = sub_col
    sub_col.where.return_value = sub_col
    sub_col.stream = _empty_async_gen

    doc_ref.collection.return_value = sub_col

    # root collection
    col_ref = MagicMock()
    col_ref.document.return_value = doc_ref
    col_ref.order_by.return_value = col_ref
    col_ref.limit.return_value = col_ref
    col_ref.where.return_value = col_ref
    col_ref.stream = _empty_async_gen

    client = MagicMock()
    client.collection.return_value = col_ref
    return client


@pytest.fixture()
def svc() -> FirestoreService:
    """Return a FirestoreService with default (not-found) mock client."""
    return FirestoreService(client=_make_client())


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------


async def test_get_user_found() -> None:
    user = _user()
    client = _make_client(snapshot_exists=True, snapshot_data=user.model_dump(mode="json"))
    result = await FirestoreService(client=client).get_user("u1")
    assert result is not None
    assert result.uid == "u1"


async def test_get_user_not_found(svc: FirestoreService) -> None:
    result = await svc.get_user("ghost")
    assert result is None


# ---------------------------------------------------------------------------
# upsert_user
# ---------------------------------------------------------------------------


async def test_upsert_user() -> None:
    client = _make_client()
    doc_ref = client.collection.return_value.document.return_value
    await FirestoreService(client=client).upsert_user(_user())
    doc_ref.set.assert_awaited_once()


# ---------------------------------------------------------------------------
# add_activity
# ---------------------------------------------------------------------------


async def test_add_activity_returns_id() -> None:
    act = _activity()
    client = _make_client()
    # Nested path: collection("users").document(uid).collection("activities").document(id)
    sub_doc_ref = (
        client.collection.return_value.document.return_value.collection.return_value.document.return_value
    )
    sub_doc_ref.set = AsyncMock(return_value=None)

    returned_id = await FirestoreService(client=client).add_activity(act)
    assert returned_id == "a1"
    sub_doc_ref.set.assert_awaited_once()


# ---------------------------------------------------------------------------
# list_activities
# ---------------------------------------------------------------------------


async def test_list_activities_empty_result(svc: FirestoreService) -> None:
    result = await svc.list_activities("u1")
    assert result == []


async def test_list_activities_with_results() -> None:
    act = _activity()
    act_data = act.model_dump(mode="json")

    async def _stream_one() -> AsyncGenerator[Any]:
        snap = MagicMock()
        snap.to_dict.return_value = act_data
        yield snap

    client = _make_client()
    # The service calls: col_ref.order_by(...).limit(...) — both should return a
    # mock whose .stream yields our document.
    query = MagicMock()
    query.limit.return_value = query
    query.where.return_value = query
    query.stream = _stream_one

    sub_col = client.collection.return_value.document.return_value.collection.return_value
    sub_col.order_by.return_value = query

    result = await FirestoreService(client=client).list_activities("u1")
    assert len(result) == 1
    assert result[0].id == "a1"


async def test_list_activities_with_before_filter() -> None:
    """list_activities passes a FieldFilter when `before` is provided."""
    client = _make_client()
    query = MagicMock()
    query.limit.return_value = query
    query.where.return_value = query
    query.stream = _empty_async_gen

    sub_col = client.collection.return_value.document.return_value.collection.return_value
    sub_col.order_by.return_value = query

    cutoff = datetime(2025, 6, 1, tzinfo=UTC)
    result = await FirestoreService(client=client).list_activities("u1", before=cutoff)
    query.where.assert_called_once()
    assert result == []


# ---------------------------------------------------------------------------
# add_insight
# ---------------------------------------------------------------------------


async def test_add_insight_returns_id() -> None:
    ins = _insight()
    client = _make_client()
    sub_doc_ref = (
        client.collection.return_value.document.return_value.collection.return_value.document.return_value
    )
    sub_doc_ref.set = AsyncMock(return_value=None)

    returned_id = await FirestoreService(client=client).add_insight(ins)
    assert returned_id == "i1"
    sub_doc_ref.set.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_recent_insights
# ---------------------------------------------------------------------------


async def test_get_recent_insights_empty(svc: FirestoreService) -> None:
    result = await svc.get_recent_insights("u1")
    assert result == []


async def test_get_recent_insights_with_results() -> None:
    ins = _insight()
    ins_data = ins.model_dump(mode="json")

    async def _stream_one() -> AsyncGenerator[Any]:
        snap = MagicMock()
        snap.to_dict.return_value = ins_data
        yield snap

    client = _make_client()
    query = MagicMock()
    query.limit.return_value = query
    query.stream = _stream_one

    sub_col = client.collection.return_value.document.return_value.collection.return_value
    sub_col.order_by.return_value = query

    result = await FirestoreService(client=client).get_recent_insights("u1")
    assert len(result) == 1
    assert result[0].id == "i1"


# ---------------------------------------------------------------------------
# add_recommendation
# ---------------------------------------------------------------------------


async def test_add_recommendation_returns_id() -> None:
    rec = _rec()
    client = _make_client()
    sub_doc_ref = (
        client.collection.return_value.document.return_value.collection.return_value.document.return_value
    )
    sub_doc_ref.set = AsyncMock(return_value=None)

    returned_id = await FirestoreService(client=client).add_recommendation(rec)
    assert returned_id == "r1"
    sub_doc_ref.set.assert_awaited_once()


# ---------------------------------------------------------------------------
# accept_recommendation
# ---------------------------------------------------------------------------


async def test_accept_recommendation_found() -> None:
    client = _make_client(snapshot_exists=True)
    # accept_recommendation navigates: collection.document.collection.document
    sub_doc_ref = (
        client.collection.return_value.document.return_value.collection.return_value.document.return_value
    )
    # Re-use the snapshot that _make_client already wired to sub_doc_ref.get
    sub_doc_ref.update = AsyncMock(return_value=None)

    result = await FirestoreService(client=client).accept_recommendation("u1", "r1")
    assert result is True
    sub_doc_ref.update.assert_awaited_once_with({"accepted": True})


async def test_accept_recommendation_not_found(svc: FirestoreService) -> None:
    # Default mock has snapshot.exists = False for all documents
    result = await svc.accept_recommendation("u1", "ghost")
    assert result is False


# ---------------------------------------------------------------------------
# fire_and_forget
# ---------------------------------------------------------------------------


async def test_fire_and_forget_returns_task() -> None:
    async def _noop() -> str:
        return "done"

    task = fire_and_forget(_noop())
    assert isinstance(task, asyncio.Task)
    await task
    assert task.result() == "done"


async def test_fire_and_forget_logs_exception_does_not_raise() -> None:
    async def _boom() -> None:
        raise ValueError("intentional failure")

    with patch("app.services.firestore_service._logger") as mock_log:
        task = fire_and_forget(_boom())
        # Let the task run to completion
        await asyncio.gather(task, return_exceptions=True)
        # Done callbacks are scheduled via call_soon — need one more loop cycle
        await asyncio.sleep(0)
        mock_log.error.assert_called_once()
        _, kwargs = mock_log.error.call_args
        assert "exc_info" in kwargs


# ---------------------------------------------------------------------------
# get_firestore_service singleton
# ---------------------------------------------------------------------------


def test_get_firestore_service_returns_same_instance() -> None:
    get_firestore_service.cache_clear()
    with patch("app.services.firestore_service.get_firestore_async_client") as mock_factory:
        mock_factory.return_value = MagicMock()
        s1 = get_firestore_service()
        s2 = get_firestore_service()
        assert s1 is s2
    get_firestore_service.cache_clear()


# ---------------------------------------------------------------------------
# get_activity
# ---------------------------------------------------------------------------


async def test_get_activity_found() -> None:
    act = _activity(aid="act-42", uid="u1")
    client = _make_client(snapshot_exists=True, snapshot_data=act.model_dump(mode="json"))
    result = await FirestoreService(client=client).get_activity("u1", "act-42")
    assert result is not None
    assert result.id == "act-42"


async def test_get_activity_not_found(svc: FirestoreService) -> None:
    result = await svc.get_activity("u1", "ghost-id")
    assert result is None


async def test_get_activity_uid_mismatch() -> None:
    # Activity stored with user_id="u2" but requested by "u1" — must return None.
    act = _activity(aid="act-99", uid="u2")
    client = _make_client(snapshot_exists=True, snapshot_data=act.model_dump(mode="json"))
    result = await FirestoreService(client=client).get_activity("u1", "act-99")
    assert result is None


# ---------------------------------------------------------------------------
# list_activities_in_range
# ---------------------------------------------------------------------------


async def test_list_activities_in_range_empty(svc: FirestoreService) -> None:
    start = datetime(2026, 6, 14, tzinfo=UTC)
    end = datetime(2026, 6, 21, tzinfo=UTC)
    result = await svc.list_activities_in_range("u1", start, end)
    assert result == []


async def test_list_activities_in_range_with_results() -> None:
    act = _activity()
    act_data = act.model_dump(mode="json")

    async def _stream_one() -> AsyncGenerator[Any]:
        snap = MagicMock()
        snap.to_dict.return_value = act_data
        yield snap

    client = _make_client()
    query = MagicMock()
    query.limit.return_value = query
    query.where.return_value = query
    query.stream = _stream_one

    sub_col = client.collection.return_value.document.return_value.collection.return_value
    sub_col.order_by.return_value = query

    start = datetime(2026, 6, 14, tzinfo=UTC)
    end = datetime(2026, 6, 21, tzinfo=UTC)
    result = await FirestoreService(client=client).list_activities_in_range("u1", start, end)
    assert len(result) == 1
    assert result[0].id == "a1"
    # Verify that .where() was called twice (start and end bounds).
    assert query.where.call_count == 2
