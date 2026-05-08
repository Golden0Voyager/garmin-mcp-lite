from garmin_mcp_lite.client import get_client


def get_events() -> dict:
    """Get upcoming race events from the Garmin calendar, including target distance and goal finish time."""
    client = get_client()

    # Use the discovered calendar events endpoint
    try:
        events = client.connectapi("/calendar-service/events")
    except Exception as e:
        return {"error": str(e)}

    result = []
    for e in events:
        custom = e.get("eventCustomization", {})
        goal = custom.get("customGoal", {})

        # Convert goal finish time from seconds to H:MM:SS
        goal_time_str = None
        if goal.get("unitType") == "time" and goal.get("value"):
            total_sec = int(goal["value"])
            h = total_sec // 3600
            m = (total_sec % 3600) // 60
            s = total_sec % 60
            goal_time_str = f"{h:d}:{m:02d}:{s:02d}"

        result.append({
            "name": e.get("eventName"),
            "date": e.get("date"),
            "type": e.get("eventType"),
            "distance_km": e.get("completionTarget", {}).get("value"),
            "goal_time": goal_time_str,
            "is_primary": custom.get("isPrimaryEvent", False),
            "training_plan_id": custom.get("trainingPlanId"),
        })

    return {
        "count": len(result),
        "events": result,
    }
