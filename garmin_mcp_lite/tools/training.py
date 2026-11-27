from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import (
    activity_local_date,
    as_dict,
    as_list,
    get_first,
    today_str,
)


def get_training_plan(date: str | None = None) -> dict:
    """Get the scheduled training workout for a specific date.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today.
    """
    client = get_client()
    if not date:
        date = today_str()

    # get_scheduled_workouts requires year and month parameters
    year, month = int(date[:4]), int(date[5:7])
    try:
        calendar_resp = client.get_scheduled_workouts(year, month)
    except Exception as e:
        return {
            "date": date,
            "has_workout": False,
            "message": f"Failed to fetch training plan: {e}",
        }

    # Extract calendarItems from the calendar service response
    items = calendar_resp.get("calendarItems", []) if isinstance(calendar_resp, dict) else []
    if not items and isinstance(calendar_resp, list):
        items = calendar_resp

    day_workouts = []
    for item in items:
        if not isinstance(item, dict):
            continue

        # Match by date
        item_date = item.get("date", "")
        if not item_date.startswith(date):
            continue

        # Filter by type: workout or training_plan only
        item_type = item.get("itemType", "").lower()
        if "workout" not in item_type and "training" not in item_type and item_type != "schedule":
            continue

        # Fetch full workout details
        workout_id = item.get("workoutId")
        if workout_id:
            try:
                # Prefer get_workout_by_id for detailed step data
                detail = client.get_workout_by_id(workout_id)
                # Back-fill basic fields if missing
                if isinstance(detail, dict):
                    if "workoutName" not in detail:
                        detail["workoutName"] = item.get("title")
                    if "sportType" not in detail and item.get("sportTypeKey"):
                        detail["sportType"] = {"sportTypeKey": item.get("sportTypeKey")}
                    day_workouts.append(detail)
                else:
                    day_workouts.append(item)
            except Exception:
                # Fall back to summary item on error
                day_workouts.append(item)
        else:
            day_workouts.append(item)

    if not day_workouts:
        return {
            "date": date,
            "has_workout": False,
            "message": "No training planned for this date.",
        }

    workout = day_workouts[0]
    sport = None
    if isinstance(workout.get("sportType"), dict):
        sport = workout.get("sportType", {}).get("sportTypeKey")
    elif workout.get("sportTypeKey"):
        sport = workout.get("sportTypeKey")

    estimated_secs = workout.get("estimatedDurationInSecs") or workout.get("estimatedDuration") or workout.get("duration")

    return {
        "date": date,
        "has_workout": True,
        "workout_id": workout.get("workoutId"),
        "name": workout.get("workoutName") or workout.get("title"),
        "sport": sport,
        "description": workout.get("description"),
        "duration_min": int(estimated_secs) // 60 if estimated_secs else None,
        "target": _extract_target(workout),
    }


def _readiness_for_day(client: Any, day: str) -> list[Any]:
    """One day's training-readiness entries; empty when the API has nothing."""
    try:
        entries = client.get_training_readiness(day)
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def get_training_status() -> dict:
    """Get current training status summary.

    Returns training status label, VO2Max, acute training load, load focus
    distribution (aerobic_low / aerobic_high / anaerobic) with 4-week targets,
    recovery time, training readiness score with factor breakdown and a
    7-day history, fitness age, and sleep score.

    Cost: ~5 API requests. Readiness is fetched in one range call; the
    per-day scan is only a fallback for Garmin builds without that endpoint.
    """
    client = get_client()
    today = today_str()

    # Fetch VO2Max using the get_max_metrics API.
    # Try multiple dates (today + recent activity dates) as the API
    # may not have data for every day.
    max_metrics = None
    dates_to_try = [today]

    # Supplement candidate dates from recent activities (avoids extra login/API calls)
    try:
        acts = client.get_activities_by_date(
            (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            today,
        ) or []
        for act in acts:
            act_date = activity_local_date(act)
            if not act_date or act_date in dates_to_try:
                continue
            dates_to_try.append(act_date)
            if len(dates_to_try) >= 5:
                break
    except Exception:
        pass

    for test_date in dates_to_try:
        try:
            max_metrics = client.get_max_metrics(test_date)
            if max_metrics:
                break
        except Exception:
            pass

    status = {}
    try:
        status = client.get_training_status(today)
    except Exception:
        status = {}

    # 解析 VO2Max（list 取首元素，dict 直接用）
    vo2max_value = None
    metrics_root = (
        max_metrics[0] if isinstance(max_metrics, list) and max_metrics
        else max_metrics if isinstance(max_metrics, dict)
        else None
    )
    if isinstance(metrics_root, dict):
        generic = metrics_root.get("generic", {})
        if isinstance(generic, dict):
            vo2max_value = generic.get("vo2MaxValue") or generic.get("vo2MaxPreciseValue")

    # ── Parse training status ────────────────────────────────────────────────
    # API response: status["mostRecentTrainingStatus"]["latestTrainingStatusData"]
    # is a dict keyed by device ID. Prefer the entry where primaryTrainingDevice=True,
    # fall back to the first entry.
    _training_status_map = {
        0: "Unknown", 1: "No Status", 2: "Overreaching", 3: "Detraining",
        4: "Maintaining", 5: "Recovery", 6: "Productive", 7: "Peaking",
        8: "Unproductive",
    }
    training_status_raw = get_first(status, "mostRecentTrainingStatus")
    training_status_value = None
    training_status_phrase = None
    if isinstance(training_status_raw, dict):
        device_map = training_status_raw.get("latestTrainingStatusData", {})
        if isinstance(device_map, dict) and device_map:
            # 优先取 primaryTrainingDevice=True 的条目
            primary = next(
                (v for v in device_map.values() if isinstance(v, dict) and v.get("primaryTrainingDevice")),
                next(iter(device_map.values()), None),
            )
            if isinstance(primary, dict):
                raw_code = primary.get("trainingStatus")
                # _training_status_map is keyed by int; non-int codes fall through to the
                # raw value exactly as the untyped .get(code, code) default always did.
                training_status_value = _training_status_map.get(raw_code, raw_code) if isinstance(raw_code, int) else raw_code
                training_status_phrase = primary.get("trainingStatusFeedbackPhrase")

    # ── Parse training load ──────────────────────────────────────────────────
    load_raw = get_first(status, "mostRecentTrainingLoadBalance")
    load_value = None
    if isinstance(load_raw, dict):
        load_value = load_raw.get("trainingLoad")

    # ── Parse training readiness (pick the most recent entry) ────────────────
    # One range call covers the week. Older garminconnect builds / mocks
    # without get_training_readiness_range fall back to the per-day scan.
    readiness = {}
    readiness_candidates: list[Any] = []
    scan_start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    try:
        range_entries = client.get_training_readiness_range(scan_start, today)
    except Exception:
        range_entries = None
    if isinstance(range_entries, list):
        readiness_candidates = [entry for entry in range_entries if isinstance(entry, dict)]
    else:
        scan_days = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        with ThreadPoolExecutor(max_workers=len(scan_days)) as pool:
            for entries in pool.map(lambda day: _readiness_for_day(client, day), scan_days):
                readiness_candidates.extend(entries)
    if readiness_candidates:
        # Sort by timestampLocal descending, pick the most recent entry
        def _ts(r):
            return r.get("timestampLocal") or r.get("timestamp") or ""
        readiness = max(readiness_candidates, key=_ts)

    # Load Focus (Training Load Balance)
    load_focus = {}
    lb_data = load_raw if isinstance(load_raw, dict) else {}
    lb_map = as_dict(lb_data.get("metricsTrainingLoadBalanceDTOMap"))
    # Find load balance stats for the primary training device
    lb_stats = None
    for _dev_id, stats in lb_map.items():
        if isinstance(stats, dict) and stats.get("primaryTrainingDevice"):
            lb_stats = stats
            break

    if lb_stats:
        load_focus = {
            "anaerobic": round(lb_stats.get("monthlyLoadAnaerobic", 0)),
            "aerobic_high": round(lb_stats.get("monthlyLoadAerobicHigh", 0)),
            "aerobic_low": round(lb_stats.get("monthlyLoadAerobicLow", 0)),
            "focus_phrase": lb_stats.get("trainingBalanceFeedbackPhrase"),
        }

    # Acute Training Load
    acute_load = None
    acwr_status = None
    acute_dto: dict[str, Any] = {}
    if isinstance(training_status_raw, dict):
        # Find acute load data for the primary training device
        device_map = training_status_raw.get("latestTrainingStatusData", {})
        primary_dev = next(
            (v for v in device_map.values() if isinstance(v, dict) and v.get("primaryTrainingDevice")),
            next(iter(device_map.values()), None),
        )
        if isinstance(primary_dev, dict):
            acute_dto = as_dict(primary_dev.get("acuteTrainingLoadDTO"))
            acute_load = acute_dto.get("dailyTrainingLoadAcute")
            acwr_status = acute_dto.get("acwrStatus")

    acute_load_detail = (
        {
            "acute": acute_load,
            "chronic": acute_dto.get("dailyTrainingLoadChronic"),
            "ratio": acute_dto.get("dailyAcuteChronicWorkloadRatio"),
            "percent": acute_dto.get("acwrPercent"),
            "status": acwr_status,
            "chronic_min": acute_dto.get("minTrainingLoadChronic"),
            "chronic_max": acute_dto.get("maxTrainingLoadChronic"),
        }
        if acute_dto
        else None
    )

    # Readiness factor breakdown and 7-day history (newest last)
    readiness_detail = None
    readiness_history: list[dict[str, Any]] = []
    if isinstance(readiness, dict) and readiness:
        readiness_detail = {
            "date": readiness.get("calendarDate"),
            "score": readiness.get("score"),
            "level": readiness.get("level"),
            "feedback_short": readiness.get("feedbackShort"),
            "feedback_long": readiness.get("feedbackLong"),
            "sleep_score": readiness.get("sleepScore"),
            "hrv_weekly_average": readiness.get("hrvWeeklyAverage"),
            "factors": {
                "sleep": {
                    "percent": readiness.get("sleepScoreFactorPercent"),
                    "feedback": readiness.get("sleepScoreFactorFeedback"),
                },
                "recovery_time": {
                    "percent": readiness.get("recoveryTimeFactorPercent"),
                    "feedback": readiness.get("recoveryTimeFactorFeedback"),
                },
                "acwr": {
                    "percent": readiness.get("acwrFactorPercent"),
                    "feedback": readiness.get("acwrFactorFeedback"),
                },
                "stress_history": {
                    "percent": readiness.get("stressHistoryFactorPercent"),
                    "feedback": readiness.get("stressHistoryFactorFeedback"),
                },
                "hrv": {
                    "percent": readiness.get("hrvFactorPercent"),
                    "feedback": readiness.get("hrvFactorFeedback"),
                },
                "sleep_history": {
                    "percent": readiness.get("sleepHistoryFactorPercent"),
                    "feedback": readiness.get("sleepHistoryFactorFeedback"),
                },
            },
        }
        for entry in readiness_candidates:
            recovery = entry.get("recoveryTime")
            readiness_history.append({
                "date": entry.get("calendarDate") or (entry.get("timestampLocal") or "")[:10] or None,
                "score": entry.get("score"),
                "level": entry.get("level"),
                "sleep_score": entry.get("sleepScore"),
                "recovery_time_h": (
                    round(recovery / 60, 1) if isinstance(recovery, (int, float)) else None
                ),
                "hrv_weekly_average": entry.get("hrvWeeklyAverage"),
            })
        readiness_history.sort(key=lambda entry: entry["date"] or "")

    # Four-week load balance with target ranges (dedicated endpoint)
    four_week_load = None
    try:
        fw_raw = as_dict(client.get_training_four_week_load_balance(today))
        fw_map = as_dict(fw_raw.get("metricsTrainingLoadBalanceDTOMap"))
        fw_stats = next(
            (v for v in fw_map.values() if isinstance(v, dict) and v.get("primaryTrainingDevice")),
            next((v for v in fw_map.values() if isinstance(v, dict)), None),
        )
        if fw_stats:
            four_week_load = {
                "date": fw_stats.get("calendarDate"),
                "feedback": fw_stats.get("trainingBalanceFeedbackPhrase"),
                "aerobic_low": {
                    "load": round(fw_stats.get("monthlyLoadAerobicLow", 0)),
                    "target_min": fw_stats.get("monthlyLoadAerobicLowTargetMin"),
                    "target_max": fw_stats.get("monthlyLoadAerobicLowTargetMax"),
                },
                "aerobic_high": {
                    "load": round(fw_stats.get("monthlyLoadAerobicHigh", 0)),
                    "target_min": fw_stats.get("monthlyLoadAerobicHighTargetMin"),
                    "target_max": fw_stats.get("monthlyLoadAerobicHighTargetMax"),
                },
                "anaerobic": {
                    "load": round(fw_stats.get("monthlyLoadAnaerobic", 0)),
                    "target_min": fw_stats.get("monthlyLoadAnaerobicTargetMin"),
                    "target_max": fw_stats.get("monthlyLoadAnaerobicTargetMax"),
                },
            }
    except Exception:
        pass

    # Fitness age and the components Garmin derives it from
    fitness_age = None
    try:
        fa_raw = as_dict(client.get_fitnessage_data(today))
        if fa_raw:
            comps = as_dict(fa_raw.get("components"))

            def _component(name: str) -> Any:
                return as_dict(comps.get(name)).get("value")

            def _round1(value: Any) -> float | None:
                return round(value, 1) if isinstance(value, (int, float)) else None

            fitness_age = {
                "chronological_age": fa_raw.get("chronologicalAge"),
                "fitness_age": _round1(fa_raw.get("fitnessAge")),
                "achievable_fitness_age": _round1(fa_raw.get("achievableFitnessAge")),
                "previous_fitness_age": _round1(fa_raw.get("previousFitnessAge")),
                "last_updated": fa_raw.get("lastUpdated"),
                "components": {
                    "resting_hr": _component("rhr"),
                    "body_fat": _component("bodyFat"),
                    "vigorous_days_avg": _component("vigorousDaysAvg"),
                    "vigorous_minutes_avg": _component("vigorousMinutesAvg"),
                },
            }
    except Exception:
        pass

    resting_hr = get_first(readiness, "restingHeartRate") if isinstance(readiness, dict) else None
    if resting_hr is None:
        with suppress(Exception):
            resting_hr = client.get_user_summary(today).get("restingHeartRate")

    return {
        "training_status": training_status_value,
        "training_status_phrase": training_status_phrase,
        "vo2max": vo2max_value,
        "acute_load": acute_load,
        "acute_load_status": acwr_status,
        "acute_load_detail": acute_load_detail,
        "load_focus": load_focus,
        "load": load_value,
        "four_week_load": four_week_load,
        "fitness_age": fitness_age,
        "readiness": readiness_detail,
        "readiness_history": readiness_history,
        "recovery_time_h": (
            round(readiness["recoveryTime"] / 60, 1)
            if isinstance(readiness, dict) and isinstance(readiness.get("recoveryTime"), (int, float))
            else None
        ),
        "recovery_time_updated_at": (
            readiness.get("timestampLocal") or readiness.get("timestamp")
            if isinstance(readiness, dict) else None
        ),
        "readiness_score": get_first(readiness, "score") if isinstance(readiness, dict) else None,
        "sleep_score": get_first(readiness, "sleepScore") if isinstance(readiness, dict) else None,
        "resting_hr": resting_hr,
        "source_dates": {
            "status": today,
            "vo2max_candidates": dates_to_try,
            "readiness": (
                get_first(readiness, "calendarDate")
                if isinstance(readiness, dict)
                else None
            ),
        },
    }


def _iter_workout_steps(steps: list[Any]):
    """Yield steps and any repeat-group children in their declared order."""
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step
        yield from _iter_workout_steps(as_list(step.get("workoutSteps")))


def _extract_target(workout: dict) -> dict:
    """Extract pace/heart-rate zone targets from a workout structure."""
    # Newer Garmin responses nest the steps under workoutSegments; older
    # payloads keep them at the top level.
    segments = as_list(workout.get("workoutSegments"))
    if segments:
        steps = [
            step
            for segment in segments
            if isinstance(segment, dict)
            for step in _iter_workout_steps(as_list(segment.get("workoutSteps")))
        ]
    else:
        steps = list(_iter_workout_steps(as_list(workout.get("workoutSteps"))))

    targets = []
    for step in steps:
        target = as_dict(step.get("targetType"))
        if target:
            targets.append({
                "step": step.get("stepOrder"),
                "type": target.get("workoutTargetTypeKey"),
                # Live payloads keep the values beside targetType; older
                # fixtures/serializers nest them inside it. Support both.
                "min": target.get("targetValue") or target.get("targetValueOne") or step.get("targetValue") or step.get("targetValueOne"),
                "max": target.get("targetValueHigh") or target.get("targetValueTwo") or step.get("targetValueHigh") or step.get("targetValueTwo"),
                "unit": target.get("targetValueUnit") or step.get("targetValueUnit"),
            })
    return {"steps": targets}

