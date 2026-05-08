from datetime import datetime, timedelta
from typing import Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import activity_type_key


def get_weekly_stats(
    period: Literal["week", "month", "year"] = "week",
) -> dict:
    """Get aggregated training volume statistics for a given period.

    Args:
        period: Time period. One of: "week" (7 days), "month" (30 days), "year" (365 days).
    """
    client = get_client()

    days = {"week": 7, "month": 30, "year": 365}[period]
    end = datetime.now()
    start = end - timedelta(days=days)

    activities = client.get_activities_by_date(
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
    ) or []

    total_distance_km = 0
    total_duration_min = 0
    total_calories = 0
    activity_counts = {}

    for act in activities:
        distance_m = act.get("distance") or 0
        duration_s = act.get("duration") or 0
        calories = act.get("calories") or 0
        type_key = activity_type_key(act) or "unknown"

        total_distance_km += distance_m / 1000
        total_duration_min += duration_s / 60
        total_calories += calories

        activity_counts[type_key] = activity_counts.get(type_key, 0) + 1

    return {
        "period": period,
        "total_activities": len(activities),
        "total_distance_km": round(total_distance_km, 1),
        "total_duration_hours": round(total_duration_min / 60, 1),
        "total_calories": int(total_calories),
        "activity_breakdown": activity_counts,
    }
