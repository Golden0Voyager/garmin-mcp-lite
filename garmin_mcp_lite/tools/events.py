from datetime import date, datetime
from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict

# The calendar endpoint is the only way to reach events on every supported
# garminconnect version. It returns the whole calendar — past events included —
# so "upcoming" has to be enforced here.
_EVENTS_ENDPOINT = "/calendar-service/events"


def _event_day(raw: Any) -> date | None:
    """Parse an event's date field; None when absent or not YYYY-MM-DD."""
    try:
        return date.fromisoformat(str(raw or "")[:10])
    except ValueError:
        return None


def get_events() -> dict:
    """Get upcoming race events from the Garmin calendar, including target distance and goal finish time.

    Events before today are dropped and the rest are returned soonest first.
    An event whose date cannot be parsed is kept at the end rather than
    silently lost.
    """
    client = get_client()

    try:
        events = client.connectapi(_EVENTS_ENDPOINT)
    except Exception as e:
        return {"error": str(e)}

    today = datetime.now().date()
    upcoming: list[tuple[date | None, dict]] = []
    for event in events or []:
        event_day = _event_day(event.get("date"))
        if event_day is not None and event_day < today:
            continue

        # Both objects come back as explicit nulls on events without a custom
        # goal, which is the common case — `.get(key, {})` does not cover it.
        custom = as_dict(event.get("eventCustomization"))
        goal = as_dict(custom.get("customGoal"))

        # Convert goal finish time from seconds to H:MM:SS
        goal_time_str = None
        if goal.get("unitType") == "time" and goal.get("value"):
            total_sec = int(goal["value"])
            h = total_sec // 3600
            m = (total_sec % 3600) // 60
            s = total_sec % 60
            goal_time_str = f"{h:d}:{m:02d}:{s:02d}"

        upcoming.append((event_day, {
            "name": event.get("eventName"),
            "date": event.get("date"),
            "type": event.get("eventType"),
            "distance_km": as_dict(event.get("completionTarget")).get("value"),
            "goal_time": goal_time_str,
            "is_primary": custom.get("isPrimaryEvent", False),
            "training_plan_id": custom.get("trainingPlanId"),
        }))

    # Real dates ascending first; undated events last (None is not comparable
    # to date, so the flag carries them past every real date).
    upcoming.sort(key=lambda pair: (pair[0] is None, pair[0] or date.max))

    return {
        "count": len(upcoming),
        "events": [item for _day, item in upcoming],
    }
