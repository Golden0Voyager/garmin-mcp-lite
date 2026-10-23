from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict

# The calendar endpoint is the only way to reach events on every supported
# garminconnect version.
_EVENTS_ENDPOINT = "/calendar-service/events"


def get_events() -> dict:
    """Get upcoming race events from the Garmin calendar, including target distance and goal finish time."""
    client = get_client()

    # Use the discovered calendar events endpoint
    try:
        events = client.connectapi(_EVENTS_ENDPOINT)
    except Exception as e:
        return {"error": str(e)}

    result: list[dict] = []
    for event in events or []:
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

        result.append({
            "name": event.get("eventName"),
            "date": event.get("date"),
            "type": event.get("eventType"),
            "distance_km": as_dict(event.get("completionTarget")).get("value"),
            "goal_time": goal_time_str,
            "is_primary": custom.get("isPrimaryEvent", False),
            "training_plan_id": custom.get("trainingPlanId"),
        })

    return {
        "count": len(result),
        "events": result,
    }
