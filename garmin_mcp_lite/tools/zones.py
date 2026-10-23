from typing import Any, Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import format_pace

_ZONE_LABELS = {1: "recovery", 2: "aerobic", 3: "tempo", 4: "threshold", 5: "anaerobic"}

_SPORT_KEYS = {
    "running": "RUNNING",
    "cycling": "CYCLING",
    "swimming": "SWIMMING",
    "default": "DEFAULT",
}


def _zone_ranges(entry: dict) -> list[dict[str, Any]]:
    """Turn Garmin's per-zone floor values into explicit [min, max] bpm ranges."""
    floors = [entry.get(f"zone{i}Floor") for i in range(1, 6)]
    max_hr = entry.get("maxHeartRateUsed")
    ranges: list[dict[str, Any]] = []
    for index, floor in enumerate(floors, start=1):
        if not isinstance(floor, (int, float)):
            continue
        next_floor = floors[index] if index < 5 else None
        upper = next_floor - 1 if isinstance(next_floor, (int, float)) else max_hr
        ranges.append({
            "zone": index,
            "label": _ZONE_LABELS[index],
            "min": int(floor),
            "max": int(upper) if isinstance(upper, (int, float)) else None,
        })
    return ranges


def get_zones(
    sport: Literal["running", "cycling", "swimming", "default"] = "running",
) -> dict:
    """Get heart rate zone boundaries and threshold values for one sport.

    Use this to interpret the heart-rate-zone durations returned by
    `garmin_activity_detail` (fields=["hrZones"]), which only contain seconds
    per zone and no boundaries.

    Args:
        sport: Which zone configuration to return. One of: running, cycling,
               swimming, default (Garmin's account-wide default).
    """
    client = get_client()
    sport_key = _SPORT_KEYS[sport]

    try:
        all_zones = client.get_heart_rate_zones()
    except Exception as e:
        return {"error": str(e)}

    result: dict[str, Any] = {"sport": sport_key}

    entry = next((z for z in all_zones or [] if isinstance(z, dict) and z.get("sport") == sport_key), None)
    if entry is None:
        result["hr_zones"] = {"error": f"No heart rate zones configured for {sport_key}."}
    else:
        result["hr_zones"] = {
            "method": entry.get("trainingMethod"),
            "max_hr": entry.get("maxHeartRateUsed"),
            "resting_hr": entry.get("restingHeartRateUsed"),
            "lthr": entry.get("lactateThresholdHeartRateUsed"),
            "zones": _zone_ranges(entry),
        }

    if sport in ("running", "default"):
        try:
            lt = client.get_lactate_threshold(latest=True)
            speed_and_hr = lt.get("speed_and_heart_rate") or {}
            power = lt.get("power") or {}
            speed = speed_and_hr.get("speed")  # m/s
            result["lactate_threshold"] = {
                "heart_rate": speed_and_hr.get("heartRate"),
                "pace_per_km": format_pace(1000 / speed) if isinstance(speed, (int, float)) and speed > 0 else None,
                "running_power_w": power.get("functionalThresholdPower"),
                "stale": power.get("isStale"),
            }
        except Exception as e:
            result["lactate_threshold"] = {"error": str(e)}

    if sport == "cycling":
        try:
            ftp = client.get_cycling_ftp()
            result["ftp"] = {
                "watts": ftp.get("functionalThresholdPower"),
                "date": (ftp.get("calendarDate") or "")[:10] or None,
                "stale": ftp.get("isStale"),
            }
        except Exception as e:
            result["ftp"] = {"error": str(e)}

    return result
