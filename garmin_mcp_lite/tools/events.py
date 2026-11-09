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

def _parse_goal_seconds(goal_time: str | None) -> int | None:
    """Parse goal time string in H:MM:SS or MM:SS to total seconds."""
    if not goal_time or not isinstance(goal_time, str):
        return None
    parts = [p.strip() for p in goal_time.split(":") if p.strip()]
    try:
        nums = [int(p) for p in parts]
        if len(nums) == 3:
            h, m, s = nums
            return h * 3600 + m * 60 + s
        if len(nums) == 2:
            m, s = nums
            return m * 60 + s
        if len(nums) == 1:
            return nums[0]
    except ValueError:
        return None
    return None


def _normalize_distance_km(target_dict: dict[str, Any]) -> float | None:
    """Convert completionTarget value to kilometers based on unit."""
    val = target_dict.get("value")
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return None
    unit = str(target_dict.get("unit") or "").lower()
    if unit == "meter":
        return round(float(val) / 1000.0, 2)
    if unit == "mile":
        return round(float(val) * 1.609344, 2)
    if unit == "yard":
        return round(float(val) * 0.0009144, 2)
    return round(float(val), 3)


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

        target = as_dict(event.get("completionTarget"))
        upcoming.append((event_day, {
            "name": event.get("eventName"),
            "date": event.get("date"),
            "type": event.get("eventType"),
            "distance_km": _normalize_distance_km(target),
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

def add_event(
    name: str,
    date: str,
    distance_km: float | None = None,
    goal_time: str | None = None,
    is_race: bool = True,
    is_primary: bool = False,
    event_type: str = "running",
    start_time: str | None = None,
    time_zone_id: str | None = None,
    location: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Add a calendar race or event to Garmin Connect.

    Args:
        name: Event name (required).
        date: Event date in YYYY-MM-DD format (required).
        distance_km: Event distance in kilometers (e.g. 21.0975 for half marathon, 42.195 for marathon).
        goal_time: Target finish time in H:MM:SS or MM:SS format (e.g. "1:32:05", "3:00:00").
        is_race: Whether this event is a race (defaults to True).
        is_primary: Whether this is the primary focus event in Garmin (defaults to False).
        event_type: Sport type (defaults to "running").
        start_time: Start time in HH:MM format (optional).
        time_zone_id: Timezone string if start_time is given (defaults to "Asia/Shanghai").
        location: City or venue location name (optional).
        note: Description or note (optional).
    """
    if not name or not str(name).strip():
        return {"error": "Event name must not be blank"}
    if not date or not _event_day(date):
        return {"error": "Invalid date format, expected YYYY-MM-DD"}

    client = get_client()

    body: dict[str, Any] = {
        "eventName": str(name).strip(),
        "date": str(date)[:10],
        "eventType": event_type,
        "race": is_race,
    }

    if start_time:
        tz = time_zone_id or "Asia/Shanghai"
        body["eventTimeLocal"] = {
            "startTimeHhMm": str(start_time).strip(),
            "timeZoneId": tz,
        }

    if distance_km is not None and distance_km > 0:
        body["completionTarget"] = {
            "value": round(float(distance_km), 4),
            "unit": "kilometer",
            "unitType": "distance",
        }

    goal_sec = _parse_goal_seconds(goal_time)
    if goal_sec is not None or is_primary:
        custom_goal = None
        if goal_sec is not None and goal_sec > 0:
            custom_goal = {
                "value": float(goal_sec),
                "unit": "second",
                "unitType": "time",
            }
        body["eventCustomization"] = {
            "customGoal": custom_goal,
            "isPrimaryEvent": is_primary,
            "isTrainingEvent": is_primary,
        }

    if location:
        body["location"] = str(location).strip()
    if note:
        body["note"] = str(note).strip()

    try:
        resp = client.client._run_request("POST", "calendar-service/event", json=body)
        data = resp.json() if hasattr(resp, "json") else resp
        return {
            "ok": True,
            "event_id": data.get("id") if isinstance(data, dict) else None,
            "name": data.get("eventName", name) if isinstance(data, dict) else name,
            "date": data.get("date", date) if isinstance(data, dict) else date,
            "distance_km": distance_km,
            "goal_time": goal_time,
            "is_primary": is_primary,
            "location": location,
        }
    except Exception as e:
        return {"error": f"Failed to add event: {e}"}


def delete_event(event_id: int | str) -> dict[str, Any]:
    """Delete a calendar event from Garmin Connect by its event ID.

    Args:
        event_id: The numeric event ID (from garmin_events).
    """
    try:
        eid = int(event_id)
    except (ValueError, TypeError):
        return {"error": f"Invalid event_id '{event_id}': expected integer"}

    client = get_client()
    try:
        client.client._run_request("DELETE", f"calendar-service/event/{eid}")
        return {"ok": True, "event_id": eid, "deleted": True}
    except Exception as e:
        return {"error": f"Failed to delete event {eid}: {e}"}
