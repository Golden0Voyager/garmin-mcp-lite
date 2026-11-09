from __future__ import annotations

from contextlib import suppress
from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict, as_list, today_str


def _is_cycling_activity(act: dict[str, Any]) -> bool:
    type_key = str(as_dict(act.get("activityType")).get("typeKey") or "").lower()
    return "cycl" in type_key or "biking" in type_key


def _format_ride_entry(summary: dict[str, Any], act_info: dict[str, Any]) -> dict[str, Any]:
    act_id = act_info.get("activityId") or summary.get("activityId")
    name = act_info.get("activityName") or summary.get("activityName")
    start_time = act_info.get("startTimeLocal") or summary.get("startTimeLocal")

    dur_s = summary.get("duration") or summary.get("movingDuration")
    dist_m = summary.get("distance")
    avg_speed = summary.get("averageMovingSpeed") or summary.get("averageSpeed")
    max_speed = summary.get("maxSpeed")

    avg_pwr = summary.get("avgPower") or summary.get("averagePower")
    max_pwr = summary.get("maxPower")
    norm_pwr = summary.get("normalizedPower")
    tss = summary.get("trainingStressScore")
    if_factor = summary.get("intensityFactor")

    avg_cad = summary.get("averageBikeCadence") or summary.get("avgCadence")
    max_cad = summary.get("maxBikeCadence") or summary.get("maxCadence")
    elev = summary.get("elevationGain")

    avg_hr = summary.get("averageHR")
    max_hr = summary.get("maxHR")
    cal = summary.get("calories")

    return {
        "id": act_id,
        "name": name,
        "date": str(start_time)[:19] if start_time else None,
        "duration_min": round(float(dur_s) / 60.0, 1) if isinstance(dur_s, (int, float)) else None,
        "distance_km": round(float(dist_m) / 1000.0, 2) if isinstance(dist_m, (int, float)) else None,
        "avg_speed_kmh": round(float(avg_speed) * 3.6, 1) if isinstance(avg_speed, (int, float)) else None,
        "max_speed_kmh": round(float(max_speed) * 3.6, 1) if isinstance(max_speed, (int, float)) else None,
        "avg_power_watts": int(avg_pwr) if isinstance(avg_pwr, (int, float)) else None,
        "max_power_watts": int(max_pwr) if isinstance(max_pwr, (int, float)) else None,
        "normalized_power_watts": int(norm_pwr) if isinstance(norm_pwr, (int, float)) else None,
        "training_stress_score": round(float(tss), 1) if isinstance(tss, (int, float)) else None,
        "intensity_factor": round(float(if_factor), 2) if isinstance(if_factor, (int, float)) else None,
        "avg_cadence": int(avg_cad) if isinstance(avg_cad, (int, float)) else None,
        "max_cadence": int(max_cad) if isinstance(max_cad, (int, float)) else None,
        "elevation_gain_m": round(float(elev), 1) if isinstance(elev, (int, float)) else None,
        "avg_hr": int(avg_hr) if isinstance(avg_hr, (int, float)) else None,
        "max_hr": int(max_hr) if isinstance(max_hr, (int, float)) else None,
        "calories": int(cal) if isinstance(cal, (int, float)) else None,
    }


def get_cycling_power(activity_id: int | None = None, limit: int = 5) -> dict[str, Any]:
    """Get cycling FTP, power load (NP, IF, TSS), cadence, and recent rides metrics.

    Args:
        activity_id: Specific cycling activity ID to inspect details for (optional).
        limit: Maximum number of recent cycling rides to return when activity_id is omitted (default: 5, max: 20).
    """
    client = get_client()

    # 1. Fetch current cycling FTP
    ftp_info: dict[str, Any] = {
        "ftp_watts": None,
        "ftp_date": None,
        "w_per_kg": None,
    }
    with suppress(Exception):
        ftp_resp = client.get_cycling_ftp()
        if isinstance(ftp_resp, dict):
            ftp_watts = ftp_resp.get("functionalThresholdPower")
            if isinstance(ftp_watts, (int, float)):
                ftp_info["ftp_watts"] = int(ftp_watts)
                ftp_info["ftp_date"] = str(ftp_resp.get("calendarDate") or "")[:10] or None

                with suppress(Exception):
                    summary = client.get_user_summary(today_str())
                    weight_kg = None
                    if isinstance(summary, dict) and summary.get("weight"):
                        weight_kg = float(summary["weight"]) / 1000.0 if float(summary["weight"]) > 500 else float(summary["weight"])
                    if weight_kg and weight_kg > 0:
                        ftp_info["w_per_kg"] = round(float(ftp_watts) / weight_kg, 2)

    # 2. Case: specific activity
    if activity_id is not None:
        try:
            detail = client.connectapi(f"/activity-service/activity/{activity_id}")
            if not isinstance(detail, dict):
                return {"error": f"Cycling activity {activity_id} not found"}
            summary = as_dict(detail.get("summaryDTO"))
            entry = _format_ride_entry(summary, detail)
            return {
                "ftp": ftp_info,
                "count": 1,
                "rides": [entry],
            }
        except Exception as e:
            return {"error": f"Failed to fetch cycling activity {activity_id}: {e}"}

    # 3. Case: list recent rides
    effective_limit = max(1, min(20, int(limit)))
    try:
        acts = as_list(client.get_activities(0, 100))
    except Exception as e:
        return {"error": f"Failed to list cycling activities: {e}"}

    cycling_acts = [a for a in acts if isinstance(a, dict) and _is_cycling_activity(a)]
    selected = cycling_acts[:effective_limit]

    results: list[dict[str, Any]] = []
    for act in selected:
        act_id = act.get("activityId")
        if not act_id:
            continue
        try:
            detail = client.connectapi(f"/activity-service/activity/{act_id}")
            summary = as_dict(detail.get("summaryDTO")) if isinstance(detail, dict) else {}
            results.append(_format_ride_entry(summary, act))
        except Exception:
            results.append(_format_ride_entry(act, act))

    return {
        "ftp": ftp_info,
        "count": len(results),
        "rides": results,
    }
