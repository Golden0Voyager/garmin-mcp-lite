from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Literal

from garmin_mcp_lite.client import get_client

# Garmin has no bulk endpoint for resting HR, so a trend costs one request per
# day (two for days without a readiness entry). Serial, a 90-day window is
# minutes of waiting and invites a 429; six workers keep it to seconds. The
# shared client is safe to read through: auth travels in headers, not cookies,
# and urllib3's connection pool is thread-safe.
_FETCH_WORKERS = 6


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
                Cost: one API request per day in the window (plus one more for
                days without a readiness entry), fetched six at a time — a 90d
                scan takes seconds, not minutes, but is still ~90 requests.
    """
    client = get_client()

    period_days = {"7d": 7, "30d": 30, "90d": 90}
    days = period_days.get(period, 7)
    end = datetime.now()
    start = end - timedelta(days=days)

    scan_dates = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
        per_day = list(pool.map(lambda day: (day, _resting_hr(client, day)), scan_dates))

    hr_data = [
        {"date": day, "value": value}
        for day, value in sorted(per_day, key=lambda pair: pair[0], reverse=True)
        if value
    ]

    values = [d["value"] for d in hr_data]
    return {
        "period": period,
        "metric": "resting",
        "date_range": f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}",
        "count": len(hr_data),
        "latest": hr_data[0] if hr_data else None,
        "average": round(sum(values) / len(values), 1) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "data": hr_data[:10],  # most recent 10 entries
    }
