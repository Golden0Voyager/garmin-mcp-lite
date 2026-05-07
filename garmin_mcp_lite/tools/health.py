from typing import Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import get_first, today_str


def get_health_data(
    metric: Literal["sleep", "hrv", "stress", "body_battery", "all"] = "all",
    date: str | None = None,
) -> dict:
    """获取健康指标数据。

    Args:
        metric: 指标类型
        date: 日期 (YYYY-MM-DD)，默认今天
    """
    client = get_client()
    if not date:
        date = today_str()

    result = {"date": date}

    if metric in ("sleep", "all"):
        try:
            sleep_raw = client.get_sleep_data(date)
            # 数据在 dailySleepDTO 子对象中
            sleep = sleep_raw.get("dailySleepDTO", {}) if isinstance(sleep_raw, dict) else {}
            result["sleep"] = {
                "score": get_first(sleep, "sleepScore", "score"),
                "duration_min": get_first(sleep, "sleepTimeInMinutes", "duration"),
                "deep_min": get_first(sleep, "deepSleepMinutes", "deep"),
                "rem_min": get_first(sleep, "remSleepMinutes", "rem"),
                "awake_count": get_first(sleep, "awakeCount", "awake"),
            }
        except Exception as e:
            result["sleep"] = {"error": str(e)}

    if metric in ("hrv", "all"):
        try:
            hrv = client.get_hrv_data(date)
            result["hrv"] = {
                "weekly_avg": get_first(hrv, "weeklyAvg", "weekly_avg"),
                "last_night_avg": get_first(hrv, "lastNightAvg", "last_night"),
                "status": get_first(hrv, "status", "hrvStatus"),
            }
        except Exception as e:
            result["hrv"] = {"error": str(e)}

    if metric in ("stress", "all"):
        try:
            stress = client.get_stress_data(date)
            result["stress"] = {
                "avg_level": get_first(stress, "avgStressLevel", "average"),
                "rest_stress": get_first(stress, "restStressLevel", "rest"),
                "stress_duration_min": get_first(stress, "stressDuration", "duration"),
            }
        except Exception as e:
            result["stress"] = {"error": str(e)}

    if metric in ("body_battery", "all"):
        try:
            bb = client.get_body_battery(date)
            values = bb.get("bodyBatteryValues", []) if isinstance(bb, dict) else []
            result["body_battery"] = {
                "last_level": (
                    values[-1].get("bodyBatteryLevel")
                    if values and isinstance(values[-1], dict)
                    else None
                ),
                "charged": get_first(bb, "bodyBatteryChargedValue", "charged"),
                "drained": get_first(bb, "bodyBatteryDrainedValue", "drained"),
            }
        except Exception as e:
            result["body_battery"] = {"error": str(e)}

    return result
