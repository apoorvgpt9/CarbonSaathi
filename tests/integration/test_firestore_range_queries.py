"""Emulator-backed regression tests for Firestore range queries.

These tests close the gap identified in Phase 8: mocked-client tests verify
that ``FirestoreService`` calls ``.where()`` with the right arguments, but they
never verify that Firestore *actually returns matching documents* for those
arguments.  The original bug (``list_activities_in_range`` used
``dt.isoformat()`` producing a ``+00:00`` suffix while stored timestamps used
Pydantic's ``model_dump(mode="json")`` ``Z`` suffix) passed all mocked tests
silently and returned zero results in production.

Invariant protected by these tests
-----------------------------------
Reverting ``_iso_z()`` in ``firestore_service.py`` back to plain
``dt.isoformat()`` MUST cause at least the following tests to fail:

* ``test_three_activities_all_returned_in_window``
* ``test_boundary_start_inclusive``
* ``test_before_cursor_filters_correctly``

because the stored ``Z``-suffixed timestamps and the query bound's
``+00:00``-suffixed timestamps diverge lexicographically in Firestore's
string-comparison mode.

All tests in this module are marked ``firestore_emulator`` and auto-skip when
the emulator is not running on ``localhost:8090``.  Run the full emulator suite
with ``make test-emulator``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.activity import Activity
from app.services.firestore_service import FirestoreService

pytestmark = pytest.mark.firestore_emulator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REF = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
"""Fixed reference timestamp used as the centre of every test window."""


def _activity(
    uid: str,
    *,
    offset: timedelta = timedelta(0),
    activity_type: str = "transport",
    emission: float = 1.0,
    raw: str = "Drove 10 km by car",
) -> Activity:
    """Build a valid :class:`~app.models.activity.Activity` for a given user.

    Args:
        uid: Firebase UID of the owning user.
        offset: Time offset from :data:`_REF` for the ``timestamp`` field.
        activity_type: Broad category (``"transport"``, ``"electricity"``, or
            ``"food"``).
        emission: Emission value in kg CO₂e.
        raw: Raw input string describing the activity.

    Returns:
        A fully-formed :class:`~app.models.activity.Activity` ready to be
        persisted via :meth:`~app.services.firestore_service.FirestoreService.add_activity`.
    """
    return Activity(
        id=str(uuid4()),
        user_id=uid,
        type=activity_type,
        timestamp=_REF + offset,
        raw_input=raw,
        structured_data={"mode": "car", "km": 10.0},
        emission_kg_co2e=emission,
        confidence="high",
        emission_factor_source="CEA 2023",
        agent_reasoning=None,
    )


# ---------------------------------------------------------------------------
# A2-1: Core regression test — three activities inside window, all returned
# ---------------------------------------------------------------------------


async def test_three_activities_all_returned_in_window(
    real_firestore_service: FirestoreService,
) -> None:
    """All three activities written inside the query window must be returned.

    This is the primary regression test for the ``_iso_z()`` bug.  The
    activities are written via :meth:`add_activity`, which calls
    ``model_dump(mode="json")`` internally — the exact production path that
    produced the original bug.  The query uses ``_iso_z()`` for its bounds.
    If ``_iso_z`` were reverted to plain ``dt.isoformat()``, the query would
    compare ``+00:00``-suffixed bounds against ``Z``-suffixed stored values,
    causing a lexicographic mismatch and returning zero results.
    """
    uid = str(uuid4())
    svc = real_firestore_service

    a1 = _activity(uid, offset=timedelta(hours=-1))
    a2 = _activity(uid, offset=timedelta(hours=-2))
    a3 = _activity(uid, offset=timedelta(hours=-3))

    for act in (a1, a2, a3):
        await svc.add_activity(act)

    window_start = _REF - timedelta(hours=6)
    window_end = _REF + timedelta(minutes=1)

    results = await svc.list_activities_in_range(uid, window_start, window_end)

    returned_ids = {r.id for r in results}
    assert a1.id in returned_ids, "Activity 1 hour before ref must be in range"
    assert a2.id in returned_ids, "Activity 2 hours before ref must be in range"
    assert a3.id in returned_ids, "Activity 3 hours before ref must be in range"
    assert len(results) == 3


# ---------------------------------------------------------------------------
# A2-2: Boundary — activity exactly at start is included (inclusive >=)
# ---------------------------------------------------------------------------


async def test_boundary_start_inclusive(
    real_firestore_service: FirestoreService,
) -> None:
    """An activity with ``timestamp == start`` must be returned (inclusive).

    The ``list_activities_in_range`` query uses ``>= _iso_z(start)``.  An
    activity stored with the same serialised timestamp as the query bound must
    therefore be included.
    """
    uid = str(uuid4())
    svc = real_firestore_service

    # One activity exactly at start, one clearly inside.
    at_start = _activity(uid, offset=timedelta(0), emission=0.5, raw="At boundary start")
    inside = _activity(uid, offset=timedelta(minutes=30), emission=1.0, raw="Inside window")

    await svc.add_activity(at_start)
    await svc.add_activity(inside)

    start = _REF
    end = _REF + timedelta(hours=1)

    results = await svc.list_activities_in_range(uid, start, end)
    returned_ids = {r.id for r in results}

    assert at_start.id in returned_ids, "Activity at exactly start must be included (inclusive >=)"
    assert inside.id in returned_ids, "Activity inside window must be included"


# ---------------------------------------------------------------------------
# A2-3: Boundary — activity exactly at end is excluded (exclusive <)
# ---------------------------------------------------------------------------


async def test_boundary_end_exclusive(
    real_firestore_service: FirestoreService,
) -> None:
    """An activity with ``timestamp == end`` must NOT be returned (exclusive <).

    The ``list_activities_in_range`` query uses ``< _iso_z(end)``.  An activity
    stored with the exact serialised ``end`` timestamp must therefore be
    excluded.
    """
    uid = str(uuid4())
    svc = real_firestore_service

    end_time = _REF + timedelta(hours=1)
    at_end = _activity(uid, offset=timedelta(hours=1), emission=0.5, raw="Exactly at end")
    inside = _activity(uid, offset=timedelta(minutes=30), emission=1.0, raw="Inside window")

    await svc.add_activity(at_end)
    await svc.add_activity(inside)

    start = _REF
    end = end_time

    results = await svc.list_activities_in_range(uid, start, end)
    returned_ids = {r.id for r in results}

    assert at_end.id not in returned_ids, "Activity at exactly end must be excluded (exclusive <)"
    assert inside.id in returned_ids, "Activity inside window must be included"


# ---------------------------------------------------------------------------
# A2-4: list_activities(before=...) cursor — second site of the same bug class
# ---------------------------------------------------------------------------


async def test_before_cursor_filters_correctly(
    real_firestore_service: FirestoreService,
) -> None:
    """``list_activities(before=cursor)`` must exclude activities at or after cursor.

    This is the second site where ``_iso_z()`` was applied — the ``before``
    cursor on ``list_activities``.  Without ``_iso_z()``, a ``+00:00``-suffixed
    bound would not match ``Z``-suffixed stored values, returning all activities
    instead of only those strictly before the cursor.
    """
    uid = str(uuid4())
    svc = real_firestore_service

    # Three activities: one before cursor, one at cursor, one after cursor.
    before_cursor = _activity(uid, offset=timedelta(hours=-2), raw="Before cursor")
    at_cursor = _activity(uid, offset=timedelta(hours=-1), raw="At cursor")
    after_cursor = _activity(uid, offset=timedelta(0), raw="At ref (after cursor)")

    for act in (before_cursor, at_cursor, after_cursor):
        await svc.add_activity(act)

    cursor = _REF - timedelta(hours=1)  # == at_cursor.timestamp
    results = await svc.list_activities(uid, limit=50, before=cursor)
    returned_ids = {r.id for r in results}

    assert before_cursor.id in returned_ids, "Activity before cursor must be returned"
    assert at_cursor.id not in returned_ids, "Activity at cursor must be excluded (strict <)"
    assert after_cursor.id not in returned_ids, "Activity after cursor must be excluded"


# ---------------------------------------------------------------------------
# A2-5: Empty window returns [] without error
# ---------------------------------------------------------------------------


async def test_empty_window_returns_empty_list(
    real_firestore_service: FirestoreService,
) -> None:
    """A query window containing no matching activities must return ``[]``.

    Activities exist in the database but entirely outside the query window;
    the service must return an empty list, not raise an exception.
    """
    uid = str(uuid4())
    svc = real_firestore_service

    # Write one activity far outside the upcoming query window.
    outside = _activity(uid, offset=timedelta(days=-10), raw="Long ago activity")
    await svc.add_activity(outside)

    # Query a narrow window near the reference time — no activities in it.
    start = _REF - timedelta(hours=1)
    end = _REF

    results = await svc.list_activities_in_range(uid, start, end)

    assert results == [], f"Expected [], got {results}"
