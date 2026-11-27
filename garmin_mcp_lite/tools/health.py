from typing import Any, Literal

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict, as_list, get_first, today_str


def _stage_minutes(sleep: dict, minutes_key: str, seconds_key: str) -> int | None:
    """Prefer explicit minute fields; Garmin's seconds fields must be divided.

    Do not guess from the value's magnitude: a 21-minute awake period is 1260
    seconds, which sits below any "looks like seconds" threshold.
    """
    value = sleep.get(minutes_key)
    if isinstance(value, (int, float)):
        return int(value)
    value = sleep.get(seconds_key)
    if isinstance(value, (int, float)):
        return int(value // 60)
    return None


def get_health_data(
    metric: Literal["sleep", "hrv", "stress", "body_battery", "spo2", "respiration", "intensity", "steps", "lifestyle", "all"] = "all",
    date: str | None = None,
) -> dict:
    """Get health metrics for a specific date.

    Args:
        metric: The health metric to retrieve. Options:
                - "sleep"        : Sleep duration, stages, score, overnight HRV,
                                   SpO2, respiration, stress and restlessness.
                - "hrv"          : HRV status, weekly average, and last-night reading.
                - "stress"       : Average and peak stress levels.
                - "body_battery" : Body battery charge/drain, peak, and current level.
                - "spo2"         : Blood oxygen saturation (average, lowest, latest).
                - "respiration"  : Respiration rate (average, min, max).
                - "intensity"    : Weekly intensity minutes vs. goal (moderate + vigorous).
                - "steps"        : Daily step count vs. goal, floors climbed, and resting HR.
                - "lifestyle"    : Garmin lifestyle-log completion counts and tracked items.
                                   Garmin exposes counts and item definitions here, not the
                                   logged quantities.
                - "all"          : All of the above combined (default).
        date: Date in YYYY-MM-DD format. Defaults to today.
    """
    client = get_client()
    if not date:
        date = today_str()

    # Annotated: the initial {"date": str} alone would infer dict[str, str], but every
    # branch below assigns a nested dict, so mypy rejects the whole function without this.
    result: dict[str, Any] = {"date": date}

    if metric in ("sleep", "all"):
        try:
            sleep_raw = as_dict(client.get_sleep_data(date))
            # 数据在 dailySleepDTO 子对象中
            sleep = as_dict(sleep_raw.get("dailySleepDTO"))
            # 睡眠分数可能在 sleepScore 或 sleepScores.overall.value 中
            scores = as_dict(sleep.get("sleepScores"))
            overall = as_dict(scores.get("overall"))
            score = sleep.get("sleepScore") if sleep.get("sleepScore") is not None else overall.get("value")

            detail: dict[str, Any] = {
                "score": score,
                "score_quality": overall.get("qualifierKey"),
                "duration_min": _stage_minutes(sleep, "sleepTimeInMinutes", "sleepTimeSeconds"),
                "deep_min": _stage_minutes(sleep, "deepSleepMinutes", "deepSleepSeconds"),
                "light_min": _stage_minutes(sleep, "lightSleepMinutes", "lightSleepSeconds"),
                "rem_min": _stage_minutes(sleep, "remSleepMinutes", "remSleepSeconds"),
                "awake_min": _stage_minutes(sleep, "awakeSleepMinutes", "awakeSleepSeconds"),
                "awake_count": get_first(sleep, "awakeCount", "awake"),
                "sleep_start_local": sleep.get("sleepStartTimestampLocal"),
                "sleep_end_local": sleep.get("sleepEndTimestampLocal"),
                "avg_spo2": sleep.get("averageSpO2Value"),
                "lowest_spo2": sleep.get("lowestSpO2Value"),
                "avg_respiration": sleep.get("averageRespirationValue"),
                "lowest_respiration": sleep.get("lowestRespirationValue"),
                "highest_respiration": sleep.get("highestRespirationValue"),
                "avg_stress": sleep.get("avgSleepStress"),
                "restless_moments": sleep_raw.get("restlessMomentsCount"),
                "avg_overnight_hrv": sleep_raw.get("avgOvernightHrv"),
                "hrv_status": sleep_raw.get("hrvStatus"),
                "body_battery_change": sleep_raw.get("bodyBatteryChange"),
                "resting_hr": sleep_raw.get("restingHeartRate"),
            }

            components = {
                key: {
                    "qualifier": as_dict(scores.get(key)).get("qualifierKey"),
                    "value": as_dict(scores.get(key)).get("value"),
                }
                for key in (
                    "deepPercentage",
                    "remPercentage",
                    "lightPercentage",
                    "restlessness",
                    "stress",
                    "awakeCount",
                    "totalDuration",
                )
                if as_dict(scores.get(key))
            }
            if components:
                detail["score_components"] = components

            result["sleep"] = detail
        except Exception as e:
            result["sleep"] = {"error": str(e)}

    if metric in ("lifestyle", "all"):
        try:
            raw = as_dict(client.get_lifestyle_logging_data(date))
            items = [
                {
                    "name": item.get("name"),
                    "category": item.get("category"),
                    "measurement_type": item.get("measurementType"),
                    "sleep_related": item.get("sleepRelated"),
                }
                for item in as_list(raw.get("dailyLogsReport"))
                if isinstance(item, dict)
            ]
            stats = [item for item in as_list(raw.get("completionStats")) if isinstance(item, dict)]
            today_stats = next(
                (item for item in stats if item.get("calendarDate") == date),
                None,
            )
            result["lifestyle"] = {
                "date": date,
                "tracked": today_stats.get("totalTracking") if today_stats else len(items),
                "completed": today_stats.get("completedTracking") if today_stats else None,
                "items": items,
                "completion_stats": [
                    {
                        "date": item.get("calendarDate"),
                        "completed": item.get("completedTracking"),
                        "tracked": item.get("totalTracking"),
                    }
                    for item in stats
                ],
            }
        except Exception as e:
            result["lifestyle"] = {"error": str(e)}

    if metric in ("hrv", "all"):
        try:
            hrv_raw = client.get_hrv_data(date)
            # HRV 数据通常在 hrvSummary 中
            hrv = as_dict(as_dict(hrv_raw).get("hrvSummary"))
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
            result["vo2max"] = as_dict(profile.get("userData")).get("vo2MaxRunning")
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
