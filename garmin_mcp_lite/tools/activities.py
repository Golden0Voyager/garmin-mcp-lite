from typing import Any, Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import (
    activity_type_key,
    as_dict,
    as_list,
    days_ago_str,
    summarize_activity,
    today_str,
)


def _weather_summary(raw: Any) -> dict:
    """Garmin fills every field with null when no station data was attached."""
    weather = as_dict(raw)
    condition = as_dict(weather.get("weatherTypeDTO"))
    fields = ("temp", "apparentTemp", "relativeHumidity", "windSpeed")
    return {
        "available": any(weather.get(field) is not None for field in fields) or bool(condition),
        "temp_c": weather.get("temp"),
        "apparent_c": weather.get("apparentTemp"),
        "humidity": weather.get("relativeHumidity"),
        "wind_speed": weather.get("windSpeed"),
        "wind_direction": weather.get("windDirectionCompassPoint") or weather.get("windDirection"),
        "condition": condition.get("desc") or condition.get("weatherType"),
    }


def _gear_summary(rows: Any) -> list[dict]:
    gear = []
    for item in as_list(rows):
        if not isinstance(item, dict):
            continue
        used = item.get("distanceUsedMeters")
        max_distance = item.get("maxUsageDistanceMeters")
        gear.append({
            "name": item.get("name"),
            "type": item.get("gearType"),
            "brand": item.get("brand"),
            "model": item.get("model"),
            "distance_used_km": round(used / 1000, 2) if isinstance(used, (int, float)) else None,
            "max_distance_km": (
                round(max_distance / 1000, 1)
                if isinstance(max_distance, (int, float)) and max_distance
                else None
            ),
            "activities_linked": item.get("numActivitiesLinked"),
        })
    return gear


def list_activities(
    start_date: str | None = None,
    end_date: str | None = None,
    activity_type: Literal["running", "cycling", "swimming", "diving", "all"] = "all",
    limit: int = 10,
) -> dict:
    """List recent activities filtered by date range and type.

    Args:
        start_date: Start date in YYYY-MM-DD format. Defaults to 7 days ago.
        end_date: End date in YYYY-MM-DD format. Defaults to today.
        activity_type: Filter by sport type. One of: running, cycling, swimming, diving, all.
        limit: Maximum number of activities to return.
    """
    client = get_client()

    if not end_date:
        end_date = today_str()
    if not start_date:
        start_date = days_ago_str(7)
    limit = max(1, limit)

    activities = client.get_activities_by_date(start_date, end_date) or []

    # 类型映射（与 sugarbee 保持一致）
    type_map = {
        "running": ["running", "treadmill_running", "trail_running"],
        "cycling": ["cycling", "road_biking", "indoor_cycling", "mountain_biking"],
        "swimming": ["swimming", "lap_swimming", "open_water_swimming"],
        "diving": ["diving", "apnea_diving", "freediving"],
    }

    filtered = []
    for act in activities:
        type_key = activity_type_key(act)

        if activity_type != "all":
            allowed = type_map.get(activity_type, [])
            if not any(a in type_key for a in allowed):
                continue

        filtered.append(summarize_activity(act))

        if len(filtered) >= limit:
            break

    return {
        "count": len(filtered),
        "period": f"{start_date} ~ {end_date}",
        "activities": filtered,
    }


def get_activity_detail(activity_id: int, fields: list[str] | None = None) -> dict:
    """Get detailed metrics for a single activity by ID.

    Args:
        activity_id: The Garmin activity ID.
        fields: Optional list of extra data sections to include.
                Supported values: "splits", "hrZones", "laps", "weather",
                "gear", "typedSplits".
                Omit to return the summary and training-load metrics only.
    """
    client = get_client()
    # garminconnect treats activity IDs as path segments; pass the str form it
    # declares so the int this MCP exposes does not trip the type checker.
    raw = client.get_activity(str(activity_id))

    # get_activity 返回的数据在 summaryDTO 子对象中
    activity = as_dict(raw.get("summaryDTO"))
    activity["activityName"] = raw.get("activityName")
    activity["activityType"] = raw.get("activityTypeDTO")
    activity["startTimeLocal"] = activity.get("startTimeLocal") or as_dict(raw.get("metadataDTO")).get("startTimeLocal")

    result = summarize_activity(activity, activity_id=activity_id)
    result.update(
        {
            "elevation_gain_m": activity.get("elevationGain"),
            "steps": int(activity["steps"]) if activity.get("steps") else None,
            "cadence": int(activity["averageRunningCadenceInStepsPerMinute"])
            if activity.get("averageRunningCadenceInStepsPerMinute")
            else None,
            "training_load": activity.get("activityTrainingLoad"),
            "training_effect": {
                "aerobic": activity.get("trainingEffect"),
                "aerobic_label": activity.get("trainingEffectLabel"),
                "aerobic_message": activity.get("aerobicTrainingEffectMessage"),
                "anaerobic": activity.get("anaerobicTrainingEffect"),
                "anaerobic_message": activity.get("anaerobicTrainingEffectMessage"),
            },
        }
    )

    # 可选扩展字段
    if fields:
        requested = set(fields)
        if "splits" in requested:
            try:
                result["splits"] = client.get_activity_splits(str(activity_id))
            except Exception as e:
                result["splits"] = {"error": str(e)}
        if "hrZones" in requested:
            try:
                result["hr_zones"] = client.get_activity_hr_in_timezones(str(activity_id))
            except Exception as e:
                result["hr_zones"] = {"error": str(e)}
        if "laps" in requested:
            try:
                result["laps"] = client.get_activity_laps(str(activity_id))
            except Exception as e:
                result["laps"] = {"error": str(e)}
        if "weather" in requested:
            try:
                result["weather"] = _weather_summary(client.get_activity_weather(str(activity_id)))
            except Exception as e:
                result["weather"] = {"error": str(e)}
        if "gear" in requested:
            try:
                result["gear"] = _gear_summary(client.get_activity_gear_v2(str(activity_id)))
            except Exception as e:
                result["gear"] = {"error": str(e)}
        if "typedSplits" in requested:
            try:
                result["typed_splits"] = client.get_activity_typed_splits(str(activity_id))
            except Exception as e:
                result["typed_splits"] = {"error": str(e)}

    return result
