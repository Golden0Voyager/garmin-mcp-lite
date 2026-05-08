from typing import Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import get_first, today_str


def get_health_data(
    metric: Literal["sleep", "hrv", "stress", "body_battery", "spo2", "respiration", "intensity", "steps", "all"] = "all",
    date: str | None = None,
) -> dict:
    """Get health metrics for a specific date.

    Args:
        metric: The health metric to retrieve. Options:
                - "sleep"        : Sleep duration, stages (deep/REM/light), and quality score.
                - "hrv"          : HRV status, weekly average, and last-night reading.
                - "stress"       : Average and peak stress levels.
                - "body_battery" : Body battery charge/drain, peak, and current level.
                - "spo2"         : Blood oxygen saturation (average, lowest, latest).
                - "respiration"  : Respiration rate (average, min, max).
                - "intensity"    : Weekly intensity minutes vs. goal (moderate + vigorous).
                - "steps"        : Daily step count vs. goal, floors climbed, and resting HR.
                - "all"          : All of the above combined (default).
        date: Date in YYYY-MM-DD format. Defaults to today.
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
            # 睡眠分数可能在 sleepScore 或 sleepScores.overall.value 中
            score = sleep.get("sleepScore")
            if score is None and "sleepScores" in sleep:
                score = sleep["sleepScores"].get("overall", {}).get("value")
            
            result["sleep"] = {
                "score": score,
                "duration_min": get_first(sleep, "sleepTimeInMinutes", "sleepTimeSeconds"),
                "deep_min": get_first(sleep, "deepSleepMinutes", "deepSleepSeconds"),
                "rem_min": get_first(sleep, "remSleepMinutes", "remSleepSeconds"),
                "awake_count": get_first(sleep, "awakeCount", "awake"),
            }
            # 如果是秒，则转换为分钟
            for k in ["duration_min", "deep_min", "rem_min"]:
                val = result["sleep"].get(k)
                if val and val > 1440:  # 超过一天说明可能是秒
                    result["sleep"][k] = int(val // 60)
        except Exception as e:
            result["sleep"] = {"error": str(e)}

    if metric in ("hrv", "all"):
        try:
            hrv_raw = client.get_hrv_data(date)
            # HRV 数据通常在 hrvSummary 中
            hrv = hrv_raw.get("hrvSummary", {}) if isinstance(hrv_raw, dict) else {}
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
                "max_level": get_first(stress, "maxStressLevel", "max"),
                "rest_stress": get_first(stress, "restStressLevel", "rest"),
            }
        except Exception as e:
            result["stress"] = {"error": str(e)}

    if metric in ("body_battery", "all"):
        try:
            bb_raw = client.get_body_battery(date)
            # Body Battery 可能是列表，取第一项
            bb = bb_raw[0] if isinstance(bb_raw, list) and bb_raw else bb_raw
            if not isinstance(bb, dict):
                bb = {}
            
            # 提取最后电量：从 bodyBatteryValuesArray 或 bodyBatteryValues
            values = get_first(bb, "bodyBatteryValuesArray", "bodyBatteryValues") or []
            last_level = None
            if values and isinstance(values[-1], (list, tuple)) and len(values[-1]) >= 2:
                last_level = values[-1][1]
            elif values and isinstance(values[-1], dict):
                last_level = values[-1].get("bodyBatteryLevel")

            result["body_battery"] = {
                "last_level": get_first(bb, "bodyBatteryMostRecentValue") or last_level,
                "charged": get_first(bb, "bodyBatteryChargedValue", "charged"),
                "drained": get_first(bb, "bodyBatteryDrainedValue", "drained"),
            }
        except Exception as e:
            result["body_battery"] = {"error": str(e)}

    if metric in ("spo2", "all"):
        try:
            spo2 = client.get_spo2_data(date)
            result["spo2"] = {
                "avg": spo2.get("averageSpO2"),
                "min": spo2.get("lowestSpO2"),
                "latest": spo2.get("latestSpO2"),
                "avg_7d": round(spo2.get("lastSevenDaysAvgSpO2", 0), 1) if spo2.get("lastSevenDaysAvgSpO2") else None,
            }
        except Exception as e:
            result["spo2"] = {"error": str(e)}

    if metric in ("respiration", "all"):
        try:
            resp = client.get_respiration_data(date)
            result["respiration"] = {
                "avg": resp.get("avgWakingRespirationValue"),
                "min": resp.get("lowestRespirationValue"),
                "max": resp.get("highestRespirationValue"),
            }
        except Exception as e:
            result["respiration"] = {"error": str(e)}

    if metric in ("intensity", "all"):
        try:
            im = client.get_intensity_minutes_data(date)
            result["intensity"] = {
                "weekly_total": im.get("weeklyTotal"),
                "weekly_goal": im.get("weekGoal"),
                "weekly_vigorous": im.get("weeklyVigorous"),
                "weekly_moderate": im.get("weeklyModerate"),
            }
        except Exception as e:
            result["intensity"] = {"error": str(e)}

    if metric == "all":
        try:
            profile = client.get_user_profile()
            result["vo2max"] = profile.get("userData", {}).get("vo2MaxRunning")
        except Exception:
            pass

    # 基础日常指标 (步数, 楼层, 静息心率)
    if metric in ("steps", "all"):
        try:
            summary = client.get_user_summary(date)
            result["daily_summary"] = {
                "steps": summary.get("totalSteps"),
                "step_goal": summary.get("dailyStepGoal"),
                "floors": summary.get("floorsAscended"),
                "floor_goal": summary.get("userFloorsAscendedGoal"),
                "resting_hr": summary.get("restingHeartRate"),
            }
        except Exception:
            pass

    return result
