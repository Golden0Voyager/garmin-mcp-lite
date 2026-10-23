from typing import Any, Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import format_duration

# Garmin's PR typeId -> (label, sport, kind). Only the endurance-relevant records
# are mapped: strength-rep and wheelchair PRs are deliberately left out so the
# payload stays small.
_RECORDS: dict[int, tuple[str, str, str]] = {
    1: ("1k", "running", "time"),
    2: ("1mile", "running", "time"),
    3: ("5k", "running", "time"),
    4: ("10k", "running", "time"),
    5: ("half_marathon", "running", "time"),
    6: ("marathon", "running", "time"),
    7: ("longest_run", "running", "distance_km"),
    8: ("longest_ride", "cycling", "distance_km"),
    9: ("max_elevation_gain", "cycling", "elevation_m"),
    10: ("max_power", "cycling", "power_w"),
    11: ("40k_cycling", "cycling", "time"),
    12: ("most_steps_day", "steps", "count"),
    13: ("most_steps_week", "steps", "count"),
    14: ("most_steps_month", "steps", "count"),
    15: ("longest_step_streak", "steps", "days"),
    16: ("current_step_streak", "steps", "days"),
    17: ("longest_pool_swim", "swimming", "distance_m"),
    18: ("100m_pool_swim", "swimming", "time"),
    19: ("100yd_pool_swim", "swimming", "time"),
    20: ("400m_pool_swim", "swimming", "time"),
    21: ("500yd_pool_swim", "swimming", "time"),
    22: ("750m_pool_swim", "swimming", "time"),
    23: ("1000m_pool_swim", "swimming", "time"),
    24: ("1000yd_pool_swim", "swimming", "time"),
    25: ("1500m_pool_swim", "swimming", "time"),
    26: ("1650yd_pool_swim", "swimming", "time"),
    27: ("most_active_seconds_day", "steps", "duration"),
}


def _format_value(kind: str, value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    if kind in ("time", "duration"):
        return format_duration(value)
    if kind == "distance_km":
        return f"{value / 1000:.2f} km"
    if kind in ("distance_m", "elevation_m"):
        return f"{int(value)} m"
    if kind == "power_w":
        return f"{int(value)} W"
    if kind == "days":
        return f"{int(value)} d"
    return f"{int(value):,}"


def _record_date(row: dict) -> str | None:
    stamp = row.get("prStartTimeLocalFormatted") or row.get("prStartTimeGmtFormatted")
    return stamp[:10] if isinstance(stamp, str) and len(stamp) >= 10 else None


def get_personal_records(
    sport: Literal["all", "running", "cycling", "swimming", "steps"] = "all",
) -> dict:
    """Get personal records (PRs) with the activity each one was set in.

    Args:
        sport: Restrict to one discipline. One of: all, running, cycling,
               swimming, steps.
    """
    client = get_client()

    try:
        raw = client.get_personal_record()
    except Exception as e:
        return {"error": str(e)}

    records: list[dict[str, Any]] = []
    for type_id in sorted(_RECORDS):
        label, record_sport, kind = _RECORDS[type_id]
        if sport != "all" and record_sport != sport:
            continue
        row = next((r for r in raw or [] if isinstance(r, dict) and r.get("typeId") == type_id), None)
        if row is None:
            continue
        value = _format_value(kind, row.get("value"))
        if value is None:
            continue
        records.append({
            "type": label,
            "value": value,
            "date": _record_date(row),
            "activity": row.get("activityName"),
        })

    return {
        "sport": sport,
        "count": len(records),
        "records": records,
    }
