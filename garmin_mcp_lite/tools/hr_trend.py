from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Literal

from garmin_mcp_lite.client import get_client

# Garmin's get_rhr_daily covers the whole window in one request. The per-day
# readiness/summary scan below is only a fallback for accounts or client
# versions where that endpoint returns nothing. Serial, a 90-day scan is
# minutes of waiting and invites a 429; six workers keep it to seconds.
_FETCH_WORKERS = 6


def _bulk_resting_hr(client: Any, start: str, end: str) -> list[dict[str, Any]]:
    """Whole-window resting HR in one request; empty when unavailable."""
    try:
        rows = client.get_rhr_daily(start, end)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    data = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = row.get("calendarDate")
        value = row.get("value")
        if day and isinstance(value, (int, float)):
            data.append({"date": day, "value": int(value)})
    return data


def _resting_hr(client: Any, day: str) -> int | None:
    """One day's resting HR: training readiness first, daily summary as fallback."""
    try:
        readiness = client.get_training_readiness(day)
        if isinstance(readiness, list) and readiness:
            rhr = readiness[0].get("restingHeartRate")
            if rhr:
                return int(rhr)
    except Exception:
        pass
    try:
        rhr = client.get_user_summary(day).get("restingHeartRate")
        if rhr:
            return int(rhr)
    except Exception:
        pass
    return None


def get_hr_trend(
    period: Literal["7d", "30d", "90d"] = "7d",
) -> dict:
    """Get resting heart rate historical trend data.

    Args:
        period: Time window. One of: "7d" (7 days), "30d" (30 days), "90d" (90 days).
                Cost: one bulk request. Only if Garmin returns no bulk data does
                it fall back to one request per day, fetched six at a time.
    """
    client = get_client()

    period_days = {"7d": 7, "30d": 30, "90d": 90}
    days = period_days.get(period, 7)
    end = datetime.now()
    start = end - timedelta(days=days - 1)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    hr_data = _bulk_resting_hr(client, start_str, end_str)

    if not hr_data:
        scan_dates = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            per_day = list(pool.map(lambda day: (day, _resting_hr(client, day)), scan_dates))
        hr_data = [
            {"date": day, "value": value}
            for day, value in per_day
            if value
        ]

    hr_data.sort(key=lambda entry: entry["date"], reverse=True)
    series = sorted(hr_data, key=lambda entry: entry["date"])

    values = [d["value"] for d in hr_data]
    return {
        "period": period,
        "metric": "resting",
        "date_range": f"{start_str} ~ {end_str}",
        "count": len(hr_data),
        "latest": hr_data[0] if hr_data else None,
        "average": round(sum(values) / len(values), 1) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "data": hr_data[:10],  # most recent 10 entries (newest first)
        "series": series,  # full window, chronological for charting
    }
