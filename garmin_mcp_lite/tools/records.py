from typing import Any, Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import (
    as_list,
    days_ago_str,
    format_duration,
    format_pace,
    today_str,
)

# Garmin's fastest-split rows use metres; these are the distances it reports.
_SPLIT_LABELS: dict[int, str] = {
    1000: "1k",
    1609: "1mile",
    5000: "5k",
    10000: "10k",
    21098: "half_marathon",
    42195: "marathon",
}

_PERIOD_DAYS = {"90d": 90, "180d": 180, "365d": 365}

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
        row = next((r for r in as_list(raw) if isinstance(r, dict) and r.get("typeId") == type_id), None)
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


def _split_label(distance: float) -> str:
    if int(distance) in _SPLIT_LABELS:
        return _SPLIT_LABELS[int(distance)]
    if distance >= 1000:
        return f"{distance / 1000:g}k"
    return f"{int(distance)}m"


def get_fastest_splits(
    period: Literal["90d", "180d", "365d"] = "365d",
    per_distance: int = 3,
) -> dict:
    """Get the fastest running split efforts Garmin recorded, by distance.

    Garmin tracks best rolling efforts at standard distances (1k, 1 mile, 5k,
    10k, half and full marathon) inside longer activities, so these are not
    the same as personal records: a 5k best can come from the middle of a
    long run.

    Args:
        period: Look-back window. One of: "90d", "180d", "365d".
        per_distance: How many top efforts to keep per distance (default 3).
    """
    client = get_client()

    days = _PERIOD_DAYS.get(period, 365)
    end = today_str()
    start = days_ago_str(days)
    per_distance = max(1, per_distance)

    try:
        raw = client.get_fastest_splits(start, end, "running", per_distance)
    except Exception as e:
        return {"error": str(e)}

    grouped: dict[float, list[dict[str, Any]]] = {}
    for row in as_list(raw):
        if not isinstance(row, dict):
            continue
        distance = row.get("distance")
        seconds = row.get("time")
        if (
            not isinstance(distance, (int, float))
            or not isinstance(seconds, (int, float))
            or seconds <= 0
            or distance <= 0
        ):
            continue
        grouped.setdefault(float(distance), []).append(row)

    splits = []
    for distance in sorted(grouped):
        rows = sorted(grouped[distance], key=lambda row: row["time"])[:per_distance]
        top = []
        for row in rows:
            seconds = float(row["time"])
            top.append({
                "time": format_duration(seconds),
                "seconds": round(seconds, 1),
                "pace": format_pace(seconds / (distance / 1000)),
                "date": row.get("activityDate"),
                "activity_id": row.get("activityId"),
            })
        best = top[0]
        splits.append({
            "distance": _split_label(distance),
            "distance_m": int(distance),
            "best_time": best["time"],
            "pace": best["pace"],
            "date": best["date"],
            "activity_id": best["activity_id"],
            "top": top,
        })

    return {
        "metric": "fastest_splits",
        "activity_type": "running",
        "period": period,
        "date_range": f"{start} ~ {end}",
        "count": len(splits),
        "splits": splits,
    }
