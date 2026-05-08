from datetime import datetime, timedelta
from typing import Literal

from garmin_mcp_lite.client import get_client


def get_hr_trend(
    period: Literal["7d", "30d", "90d"] = "7d",
) -> dict:
    """Get resting heart rate historical trend data.

    Args:
        period: Time window. One of: "7d" (7 days), "30d" (30 days), "90d" (90 days).
    """
    client = get_client()

    period_days = {"7d": 7, "30d": 30, "90d": 90}
    days = period_days.get(period, 7)
    end = datetime.now()
    start = end - timedelta(days=days)

    raw_rows: list[dict] = []
    for i in range(days):
        check_date = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        rhr = None
        try:
            # Method 1: via training readiness
            readiness_list = client.get_training_readiness(check_date)
            if isinstance(readiness_list, list) and readiness_list:
                rhr = readiness_list[0].get("restingHeartRate")
        except Exception:
            pass

        if not rhr:
            try:
                # Method 2: via daily summary (more universal)
                summary = client.get_user_summary(check_date)
                rhr = summary.get("restingHeartRate")
            except Exception:
                pass

        if rhr:
            raw_rows.append({"date": check_date, "value": int(rhr)})

    # Aggregate by date and sort to ensure stable 'latest' semantics
    by_date: dict[str, list[int]] = {}
    for row in raw_rows:
        by_date.setdefault(row["date"], []).append(row["value"])

    hr_data = [
        {"date": date, "value": round(sum(values) / len(values), 1)}
        for date, values in by_date.items()
    ]
    hr_data.sort(key=lambda x: x["date"], reverse=True)

    # Compute summary statistics
    values = [d["value"] for d in hr_data if d["value"]]
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
