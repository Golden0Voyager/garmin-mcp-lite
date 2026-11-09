from __future__ import annotations

from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict, as_list, today_str


def get_hrv_status(date: str | None = None) -> dict[str, Any]:
    """Get overnight HRV (Heart Rate Variability) status, baseline, and recovery guidance.

    Args:
        date: Date in YYYY-MM-DD format (defaults to today).
    """
    client = get_client()
    target_date = date.strip() if date and date.strip() else today_str()

    try:
        data = client.get_hrv_data(target_date)
    except Exception as e:
        return {"error": f"Failed to fetch HRV data: {e}"}

    if not isinstance(data, dict):
        return {"date": target_date, "status": "NO_DATA", "message": "No HRV data available for this date"}

    summary = as_dict(data.get("hrvSummary"))
    if not summary:
        return {"date": target_date, "status": "NO_DATA", "message": "No HRV summary available for this date"}

    status = summary.get("status") or "NONE"
    weekly_avg = summary.get("weeklyAvg")
    last_night_avg = summary.get("lastNightAvg")
    last_night_high = summary.get("lastNight5MinHigh")

    baseline_dict = as_dict(summary.get("baseline"))
    balanced_low = baseline_dict.get("balancedLow")
    balanced_upper = baseline_dict.get("balancedUpper")

    baseline_info: dict[str, Any] = {
        "balanced_low": balanced_low,
        "balanced_upper": balanced_upper,
        "range_ms": f"{balanced_low} - {balanced_upper} ms" if balanced_low is not None and balanced_upper is not None else None,
    }

    status_upper = str(status).upper()
    if status_upper == "BALANCED":
        guidance = "HRV处于平衡区间，自主神经系统恢复良好，可按计划执行高强度或长距离训练。"
    elif status_upper == "UNBALANCED":
        guidance = "HRV偏离个人动态基线，提示自主神经存在累积疲劳或未充分恢复，建议监控体感，重点训练可考虑温和降阶。"
    elif status_upper in ("LOW", "POOR"):
        guidance = "HRV显著低于基准线，身体处于较深疲劳状态，强烈建议安排轻松排酸恢复跑或完全休息。"
    else:
        guidance = "HRV基线建立中，请保持佩戴手表入睡以建立专属基线。"

    readings = as_list(data.get("hrvReadings"))

    return {
        "date": summary.get("calendarDate") or target_date,
        "status": status,
        "weekly_avg_ms": weekly_avg,
        "last_night_avg_ms": last_night_avg,
        "last_night_5min_high_ms": last_night_high,
        "baseline": baseline_info,
        "feedback_phrase": summary.get("feedbackPhrase"),
        "training_guidance": guidance,
        "readings_sample_count": len(readings),
    }
