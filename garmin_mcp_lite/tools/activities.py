from typing import Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import (
    activity_type_key,
    days_ago_str,
    summarize_activity,
    today_str,
)


def list_activities(
    start_date: str | None = None,
    end_date: str | None = None,
    activity_type: Literal["running", "cycling", "swimming", "diving", "all"] = "all",
    limit: int = 10,
) -> dict:
    """获取活动列表，支持按日期范围和类型筛选。

    Args:
        start_date: 开始日期 (YYYY-MM-DD)，默认7天前
        end_date: 结束日期 (YYYY-MM-DD)，默认今天
        activity_type: 活动类型过滤
        limit: 返回条数上限
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
    """获取单次活动详情。

    Args:
        activity_id: 活动ID
        fields: 指定返回字段，如 ["splits", "hrZones", "laps", "gps"]
                默认返回基础摘要
    """
    client = get_client()
    raw = client.get_activity(activity_id)

    # get_activity 返回的数据在 summaryDTO 子对象中
    activity = raw.get("summaryDTO", {})
    activity["activityName"] = raw.get("activityName")
    activity["activityType"] = raw.get("activityTypeDTO")
    activity["startTimeLocal"] = raw.get("metadataDTO", {}).get("startTimeLocal")

    result = summarize_activity(activity, activity_id=activity_id)
    result.update(
        {
            "elevation_gain_m": activity.get("elevationGain"),
            "steps": int(activity["steps"]) if activity.get("steps") else None,
            "cadence": int(activity["averageRunningCadenceInStepsPerMinute"])
            if activity.get("averageRunningCadenceInStepsPerMinute")
            else None,
        }
    )

    # 可选扩展字段
    if fields:
        requested = set(fields)
        if "splits" in requested:
            try:
                result["splits"] = client.get_activity_splits(activity_id)
            except Exception as e:
                result["splits"] = {"error": str(e)}
        if "hrZones" in requested:
            try:
                result["hr_zones"] = client.get_activity_hr_in_timezones(activity_id)
            except Exception as e:
                result["hr_zones"] = {"error": str(e)}
        if "laps" in requested:
            try:
                result["laps"] = client.get_activity_laps(activity_id)
            except Exception as e:
                result["laps"] = {"error": str(e)}

    return result
