"""Dashboard route for CarbonSaathi.

Aggregates the authenticated user's carbon activity data into a single
summary response covering today's totals, a rolling 7-day breakdown, a
consecutive-day streak, and a lifetime activity count.

All date calculations are performed in Indian Standard Time (IST, Asia/Kolkata,
UTC+05:30) so that the dashboard reflects the user's local calendar day.

Routes
------
- ``GET /api/dashboard`` — full dashboard summary
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import CurrentUser, verify_firebase_token
from app.models.activity import Activity
from app.services.firestore_service import FirestoreService, get_firestore_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

IST = ZoneInfo("Asia/Kolkata")

# v1 cap: lifetime_activity_count is derived from a bounded Firestore read.
# Activities beyond 1 000 are not counted.  Document this limit to users.
_LIFETIME_LIMIT: int = 1000


class DashboardByType(BaseModel):
    """Emission breakdown by activity category for a single period.

    Attributes:
        transport_kg: Total transport CO₂e in kg.
        electricity_kg: Total electricity CO₂e in kg.
        food_kg: Total food CO₂e in kg.
    """

    transport_kg: float
    electricity_kg: float
    food_kg: float


class DashboardDayBreakdown(BaseModel):
    """Emission total for a single IST calendar day.

    Attributes:
        date_ist: The calendar date in IST (``YYYY-MM-DD``).
        total_kg: Total CO₂e emitted on that day in kg.
    """

    date_ist: date
    total_kg: float


class DashboardResponse(BaseModel):
    """Complete dashboard summary response.

    Attributes:
        today_kg: Total CO₂e emitted today (IST) in kg.
        today_by_type: Today's emissions split by activity category.
        week_total_kg: Total CO₂e over the last 7 IST days (today + 6 prior).
        week_by_day: Per-day breakdown for the 7-day window, oldest → today.
        streak_days: Number of consecutive IST days (ending today or yesterday)
            on which at least one activity was logged.
        lifetime_activity_count: Total activities ever logged (capped at
            :data:`_LIFETIME_LIMIT` for v1).
    """

    today_kg: float
    today_by_type: DashboardByType
    week_total_kg: float
    week_by_day: list[DashboardDayBreakdown]
    streak_days: int
    lifetime_activity_count: int


def _round2(value: float) -> float:
    """Round a float to 2 decimal places for display.

    Args:
        value: The value to round.

    Returns:
        ``value`` rounded to 2 decimal places.
    """
    return round(value, 2)


def _compute_streak(activities: list[Activity], today_ist: date) -> int:
    """Compute the consecutive-day activity streak ending on or before today.

    The streak walks backward from ``today_ist``.  If today has no activity,
    a "same-day grace" applies: the walk starts from yesterday instead, so a
    user who logged yesterday and the day before still shows streak=2.  If
    yesterday also has no activity the streak is 0.

    Args:
        activities: All activities to consider (typically the last 200).
        today_ist: Today's date in IST.

    Returns:
        The length of the consecutive streak in days.
    """
    dates_set = {a.timestamp.astimezone(IST).date() for a in activities}

    streak = 0
    cursor = today_ist
    if today_ist not in dates_set:
        cursor = today_ist - timedelta(days=1)

    while cursor in dates_set:
        streak += 1
        cursor -= timedelta(days=1)

    return streak


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Get activity dashboard",
)
async def get_dashboard(
    current: Annotated[CurrentUser, Depends(verify_firebase_token)],
    service: Annotated[FirestoreService, Depends(get_firestore_service)],
) -> DashboardResponse:
    """Return an aggregated carbon dashboard for the authenticated user.

    Fetches activities over the rolling 7-day IST window plus a recent sample
    for streak calculation, then aggregates by type and IST day.

    All date boundaries are computed in IST and converted to UTC before
    querying Firestore.

    Args:
        current: The authenticated Firebase user.
        service: The Firestore persistence layer.

    Returns:
        A :class:`DashboardResponse` with today's totals, weekly breakdown,
        streak, and lifetime count.
    """
    now_ist = datetime.now(UTC).astimezone(IST)
    today_ist_date: date = now_ist.date()

    # 7-day window: [today-6 days at 00:00 IST, tomorrow at 00:00 IST)
    week_start_ist = datetime(
        today_ist_date.year,
        today_ist_date.month,
        today_ist_date.day,
        tzinfo=IST,
    ) - timedelta(days=6)
    week_end_ist = datetime(
        today_ist_date.year,
        today_ist_date.month,
        today_ist_date.day,
        tzinfo=IST,
    ) + timedelta(days=1)

    week_start_utc = week_start_ist.astimezone(UTC)
    week_end_utc = week_end_ist.astimezone(UTC)

    # Fetch week activities and recent activities for streak in parallel would
    # require asyncio.gather; use sequential calls for simplicity (two queries).
    week_activities = await service.list_activities_in_range(
        current.uid, week_start_utc, week_end_utc, limit=200
    )
    # Most recent 200 activities for streak calculation (v1 reasonable limit).
    streak_activities = await service.list_activities(current.uid, limit=200)
    # Lifetime count: bounded read (v1 cap = 1 000).
    lifetime_activities = await service.list_activities(current.uid, limit=_LIFETIME_LIMIT)

    # ------------------------------------------------------------------
    # Streak
    # ------------------------------------------------------------------
    streak_days = _compute_streak(streak_activities, today_ist_date)

    # ------------------------------------------------------------------
    # Week-by-day bucketing
    # ------------------------------------------------------------------
    day_totals: dict[date, float] = defaultdict(float)
    for activity in week_activities:
        ist_date = activity.timestamp.astimezone(IST).date()
        day_totals[ist_date] += activity.emission_kg_co2e

    # Build week_by_day oldest (index 0) → today (index 6).
    week_by_day: list[DashboardDayBreakdown] = []
    for offset in range(6, -1, -1):
        day = today_ist_date - timedelta(days=offset)
        week_by_day.append(
            DashboardDayBreakdown(date_ist=day, total_kg=_round2(day_totals.get(day, 0.0)))
        )

    # ------------------------------------------------------------------
    # Today's totals by type
    # ------------------------------------------------------------------
    today_transport = 0.0
    today_electricity = 0.0
    today_food = 0.0

    for activity in week_activities:
        if activity.timestamp.astimezone(IST).date() != today_ist_date:
            continue
        if activity.type == "transport":
            today_transport += activity.emission_kg_co2e
        elif activity.type == "electricity":
            today_electricity += activity.emission_kg_co2e
        else:
            today_food += activity.emission_kg_co2e

    today_kg = _round2(today_transport + today_electricity + today_food)
    week_total_kg = _round2(sum(a.emission_kg_co2e for a in week_activities))

    return DashboardResponse(
        today_kg=today_kg,
        today_by_type=DashboardByType(
            transport_kg=_round2(today_transport),
            electricity_kg=_round2(today_electricity),
            food_kg=_round2(today_food),
        ),
        week_total_kg=week_total_kg,
        week_by_day=week_by_day,
        streak_days=streak_days,
        lifetime_activity_count=len(lifetime_activities),
    )
