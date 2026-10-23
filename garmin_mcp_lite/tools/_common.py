from __future__ import annotations

from datetime import datetime, timedelta


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def days_ago_str(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def get_first(d: dict | None, *keys: str):
    if not isinstance(d, dict):
        return None
    for key in keys:
        if key in d:
            return d[key]
    return None


def pace_from_speed(avg_speed: float | int | None) -> str | None:
    if not avg_speed or avg_speed <= 0:
        return None
    pace_s_per_km = 1000 / float(avg_speed)
    return f"{int(pace_s_per_km // 60):02d}:{int(pace_s_per_km % 60):02d}"


def format_duration(seconds: float | int | None) -> str | None:
    """Format a duration in seconds as M:SS, or H:MM:SS once it reaches an hour."""
    if seconds is None:
        return None
    total = int(round(float(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_pace(seconds_per_km: float | int | None) -> str | None:
    """Format a per-kilometre pace as zero-padded MM:SS, matching pace_from_speed."""
    if not seconds_per_km or seconds_per_km <= 0:
        return None
    total = int(round(float(seconds_per_km)))
    return f"{total // 60:02d}:{total % 60:02d}"


def activity_type_key(activity: dict) -> str:
    return (activity.get("activityType") or {}).get("typeKey", "").lower()


def activity_local_date(activity: dict) -> str | None:
    start = activity.get("startTimeLocal")
    if isinstance(start, str) and len(start) >= 10:
        return start[:10]
    return None


def summarize_activity(activity: dict, activity_id: int | None = None) -> dict:
    activity_id = activity_id if activity_id is not None else activity.get("activityId")
    distance_m = activity.get("distance")
    duration_s = activity.get("duration")
    return {
        "id": activity_id,
        "name": activity.get("activityName"),
        "type": activity_type_key(activity),
        "date": activity.get("startTimeLocal"),
        "distance_km": round(distance_m / 1000, 2) if distance_m else None,
        "duration_min": int(duration_s // 60) if duration_s else None,
        "calories": int(activity["calories"]) if activity.get("calories") else None,
        "avg_hr": int(activity["averageHR"]) if activity.get("averageHR") else None,
        "max_hr": int(activity["maxHR"]) if activity.get("maxHR") else None,
        "pace": pace_from_speed(activity.get("averageSpeed")),
        "vo2max": activity.get("vO2MaxValue"),
    }
