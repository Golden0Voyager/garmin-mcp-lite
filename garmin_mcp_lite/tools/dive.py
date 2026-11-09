from __future__ import annotations

from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict, as_list

_DIVE_TYPE_NAMES = {
    "apnea_diving": "自由潜水",
    "single_gas_diving": "单气水肺潜水",
    "multi_gas_diving": "多气体水肺潜水",
    "gauge_diving": "仪表潜水",
    "ccr_diving": "密闭循环潜水 (CCR)",
}


def _is_dive_activity(act: dict[str, Any]) -> bool:
    """Check if an activity is a diving activity (apnea or scuba)."""
    type_key = str(as_dict(act.get("activityType")).get("typeKey") or "").lower()
    return any(k in type_key for k in ("div", "apnea"))


def _format_dive_entry(summary: dict[str, Any], act_info: dict[str, Any]) -> dict[str, Any]:
    """Extract and format dive metrics from summaryDTO and activity metadata."""
    act_id = act_info.get("activityId") or summary.get("activityId")
    name = act_info.get("activityName") or summary.get("activityName")
    start_time = act_info.get("startTimeLocal") or summary.get("startTimeLocal")

    type_key = str(as_dict(act_info.get("activityType")).get("typeKey") or "").lower()
    if not type_key:
        type_key = str(as_dict(summary.get("activityType")).get("typeKey") or "diving").lower()

    type_name = _DIVE_TYPE_NAMES.get(type_key, "潜水")

    max_depth = summary.get("maxDepth")
    avg_depth = summary.get("averageDepth")
    bottom_time = summary.get("bottomTime")
    max_bottom = summary.get("maxBottomTime")
    surf_interval = summary.get("surfaceInterval")

    avg_temp = summary.get("averageTemperature") or summary.get("minTemperature")
    min_hr = summary.get("minHR")
    avg_hr = summary.get("averageHR")
    max_hr = summary.get("maxHR")
    dive_count = summary.get("diveCount")
    training_load = summary.get("activityTrainingLoad")

    return {
        "id": act_id,
        "name": name,
        "date": str(start_time)[:19] if start_time else None,
        "type": type_key,
        "type_name": type_name,
        "max_depth_m": round(float(max_depth), 2) if isinstance(max_depth, (int, float)) else None,
        "avg_depth_m": round(float(avg_depth), 2) if isinstance(avg_depth, (int, float)) else None,
        "dive_count": int(dive_count) if isinstance(dive_count, (int, float)) else None,
        "bottom_time_min": round(float(bottom_time) / 60.0, 1) if isinstance(bottom_time, (int, float)) else None,
        "max_bottom_time_s": round(float(max_bottom), 1) if isinstance(max_bottom, (int, float)) else None,
        "surface_interval_min": round(float(surf_interval) / 60.0, 1) if isinstance(surf_interval, (int, float)) else None,
        "water_temp_c": round(float(avg_temp), 1) if isinstance(avg_temp, (int, float)) else None,
        "min_hr": int(min_hr) if isinstance(min_hr, (int, float)) else None,
        "avg_hr": int(avg_hr) if isinstance(avg_hr, (int, float)) else None,
        "max_hr": int(max_hr) if isinstance(max_hr, (int, float)) else None,
        "training_load": round(float(training_load), 1) if isinstance(training_load, (int, float)) else None,
    }


def get_dive_logs(limit: int = 5, activity_id: int | None = None) -> dict[str, Any]:
    """Get freediving and scuba diving logs and metrics (depth, bottom time, water temperature, dive reflex HR).

    Args:
        limit: Number of recent dive activities to return (default: 5, max: 20).
        activity_id: Specific dive activity ID to fetch details for (optional).
    """
    client = get_client()

    # Case 1: Specific activity ID
    if activity_id is not None:
        try:
            detail = client.connectapi(f"/activity-service/activity/{activity_id}")
            if not isinstance(detail, dict):
                return {"error": f"Dive activity {activity_id} not found"}
            summary = as_dict(detail.get("summaryDTO"))
            entry = _format_dive_entry(summary, detail)
            return {"count": 1, "dives": [entry]}
        except Exception as e:
            return {"error": f"Failed to fetch dive activity {activity_id}: {e}"}

    # Case 2: Recent dive activities list
    effective_limit = max(1, min(20, int(limit)))
    try:
        # Search recent activities (up to 200 activities to find dive sessions)
        acts = as_list(client.get_activities(0, 150))
    except Exception as e:
        return {"error": f"Failed to list dive activities: {e}"}

    dive_acts = [a for a in acts if isinstance(a, dict) and _is_dive_activity(a)]
    selected_acts = dive_acts[:effective_limit]

    results: list[dict[str, Any]] = []
    for act in selected_acts:
        act_id = act.get("activityId")
        if not act_id:
            continue
        try:
            # Fetch detailed summary metrics for dive stats
            detail = client.connectapi(f"/activity-service/activity/{act_id}")
            summary = as_dict(detail.get("summaryDTO")) if isinstance(detail, dict) else {}
            results.append(_format_dive_entry(summary, act))
        except Exception:
            # Fall back to top-level activity summary
            results.append(_format_dive_entry(act, act))

    return {
        "count": len(results),
        "dives": results,
    }
