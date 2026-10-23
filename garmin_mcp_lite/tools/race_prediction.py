from datetime import datetime, timedelta
from typing import Any, Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import format_duration, format_pace

# API field -> (display name, race distance in km, used to derive pace)
_DISTANCES: dict[str, tuple[str, float]] = {
    "time5K": ("5k", 5.0),
    "time10K": ("10k", 10.0),
    "timeHalfMarathon": ("half_marathon", 21.0975),
    "timeMarathon": ("marathon", 42.195),
}

_WINDOW_DAYS = {"90d": 90, "1y": 365}


def _build_predictions(row: dict) -> dict[str, dict[str, str | None]]:
    predictions: dict[str, dict[str, str | None]] = {}
    for field, (label, distance_km) in _DISTANCES.items():
        seconds = row.get(field)
        # Narrowing has to happen inline: a boolean alias (`has_time`) is not
        # enough for mypy to accept `seconds / distance_km`.
        if isinstance(seconds, (int, float)) and seconds > 0:
            predictions[label] = {
                "time": format_duration(seconds),
                "pace_per_km": format_pace(seconds / distance_km),
            }
        else:
            predictions[label] = {"time": None, "pace_per_km": None}
    return predictions


def _rows(raw: Any) -> list[dict]:
    """Normalise the single-row and range responses into a list of dicts."""
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def get_race_prediction(period: Literal["today", "90d", "1y"] = "today") -> dict:
    """Predict finish times for the 5K, 10K, half marathon and marathon.

    Garmin derives these from recent running activities, so an account with no
    recent runs returns nothing.

    Args:
        period: "today" returns the current prediction only. "90d" or "1y" also
                reports how each prediction moved across that window
                (change_s is negative when the athlete got faster).
    """
    client = get_client()

    if period == "today":
        try:
            rows = _rows(client.get_race_predictions())
        except Exception as e:
            return {"error": str(e)}
        if not rows:
            return {"error": "Garmin returned no race prediction. A recent run is usually required."}
        latest = max(rows, key=lambda r: r.get("calendarDate") or "")
        return {
            "date": latest.get("calendarDate"),
            "predictions": _build_predictions(latest),
        }

    days = _WINDOW_DAYS.get(period, 90)
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        rows = _rows(
            client.get_race_predictions(
                startdate=start.strftime("%Y-%m-%d"),
                enddate=end.strftime("%Y-%m-%d"),
                _type="monthly",
            )
        )
    except Exception as e:
        return {"error": str(e)}
    if not rows:
        return {"error": f"Garmin returned no race prediction for the last {days} days."}

    latest = max(rows, key=lambda r: r.get("calendarDate") or "")
    earliest = min(rows, key=lambda r: r.get("calendarDate") or "")

    change_s: dict[str, int | None] = {}
    for field, (label, _distance_km) in _DISTANCES.items():
        new, old = latest.get(field), earliest.get(field)
        change_s[label] = (
            int(round(new - old))
            if isinstance(new, (int, float)) and isinstance(old, (int, float))
            else None
        )

    return {
        "date": latest.get("calendarDate"),
        "predictions": _build_predictions(latest),
        "trend": {"since": earliest.get("calendarDate"), "change_s": change_s},
    }
