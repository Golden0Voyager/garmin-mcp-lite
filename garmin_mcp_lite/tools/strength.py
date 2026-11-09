from __future__ import annotations

from contextlib import suppress
from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict, as_list

_EXERCISE_MUSCLE_MAP: dict[str, str] = {
    "SQUAT": "legs_glutes",
    "LUNGE": "legs_glutes",
    "LEG_PRESS": "legs_glutes",
    "LEG_EXTENSION": "legs_glutes",
    "LEG_CURL": "legs_glutes",
    "CALF_RAISE": "legs_glutes",
    "DEADLIFT": "legs_glutes",
    "HIP_THRUST": "legs_glutes",
    "BENCH_PRESS": "upper_body",
    "CHEST_PRESS": "upper_body",
    "PUSH_UP": "upper_body",
    "FLY": "upper_body",
    "SHOULDER_PRESS": "upper_body",
    "LATERAL_RAISE": "upper_body",
    "TRICEPS_EXTENSION": "upper_body",
    "DIP": "upper_body",
    "BICEPS_CURL": "upper_body",
    "ROW": "upper_body",
    "PULL_UP": "upper_body",
    "PULLDOWN": "upper_body",
    "PLANK": "core",
    "CRUNCH": "core",
    "SIT_UP": "core",
    "RUSSIAN_TWIST": "core",
    "LEG_RAISE": "core",
}


def _is_strength_activity(act: dict[str, Any]) -> bool:
    type_key = str(as_dict(act.get("activityType")).get("typeKey") or "").lower()
    return "strength" in type_key


def _classify_exercise_category(category: str | None) -> str:
    if not category:
        return "other"
    cat_upper = category.upper()
    for key, group in _EXERCISE_MUSCLE_MAP.items():
        if key in cat_upper:
            return group
    return "other"


def _format_strength_session(act_info: dict[str, Any], sets_data: dict[str, Any] | None) -> dict[str, Any]:
    act_id = act_info.get("activityId")
    name = act_info.get("activityName")
    start_time = act_info.get("startTimeLocal")

    summary = as_dict(act_info.get("summaryDTO")) or act_info
    dur_s = summary.get("duration")
    avg_hr = summary.get("averageHR")
    max_hr = summary.get("maxHR")
    cal = summary.get("calories")
    load = summary.get("activityTrainingLoad")

    raw_sets = as_list(as_dict(sets_data).get("exerciseSets")) if sets_data else []

    active_sets_count = 0
    rest_sets_count = 0
    total_reps = 0
    total_volume_kg = 0.0
    active_dur_s = 0.0
    rest_dur_s = 0.0

    muscle_counts: dict[str, int] = {
        "legs_glutes": 0,
        "upper_body": 0,
        "core": 0,
        "other": 0,
    }
    exercise_list: list[dict[str, Any]] = []

    for s in raw_sets:
        if not isinstance(s, dict):
            continue
        set_type = s.get("setType")
        dur = float(s.get("duration") or 0.0)

        if set_type == "REST":
            rest_sets_count += 1
            rest_dur_s += dur
            continue

        # ACTIVE set
        active_sets_count += 1
        active_dur_s += dur
        reps = int(s.get("repetitionCount") or 0)
        total_reps += reps

        raw_weight = float(s.get("weight") or 0.0)
        weight_kg = (raw_weight / 1000.0) if raw_weight > 500 else raw_weight
        if weight_kg > 0 and reps > 0:
            total_volume_kg += weight_kg * reps

        exercises = as_list(s.get("exercises"))
        cat = exercises[0].get("category") if exercises and isinstance(exercises[0], dict) else None
        ex_name = exercises[0].get("name") if exercises and isinstance(exercises[0], dict) else None

        muscle_group = _classify_exercise_category(cat)
        muscle_counts[muscle_group] += 1

        exercise_list.append({
            "category": cat or "UNKNOWN",
            "name": ex_name,
            "muscle_group": muscle_group,
            "reps": reps,
            "weight_kg": round(weight_kg, 1),
            "duration_s": round(dur, 1),
        })

    # Fallback to summaryDTO activeSets if exerciseSets not populated
    if active_sets_count == 0 and summary.get("activeSets"):
        active_sets_count = int(summary["activeSets"])

    has_leg_training = muscle_counts["legs_glutes"] > 0
    if has_leg_training:
        fatigue_alert = "涉及下肢与臀腿负重训练，动力链微损伤处于恢复窗口。建议次日避免安排高强度乳酸门槛跑或长距离LSD，优先安排轻松有氧慢跑(E跑)或休整。"
    else:
        fatigue_alert = "主要为上肢、背部或核心稳定性训练，对下肢跑步推进肌群负担较小，次日可正常按计划执行跑步训练。"

    return {
        "id": act_id,
        "name": name,
        "date": str(start_time)[:19] if start_time else None,
        "duration_min": round(float(dur_s) / 60.0, 1) if isinstance(dur_s, (int, float)) else None,
        "active_sets": active_sets_count,
        "rest_sets": rest_sets_count,
        "total_reps": total_reps if total_reps > 0 else None,
        "total_volume_kg": round(total_volume_kg, 1) if total_volume_kg > 0 else None,
        "muscle_group_distribution": muscle_counts,
        "runner_fatigue_alert": fatigue_alert,
        "avg_hr": int(avg_hr) if isinstance(avg_hr, (int, float)) else None,
        "max_hr": int(max_hr) if isinstance(max_hr, (int, float)) else None,
        "calories": int(cal) if isinstance(cal, (int, float)) else None,
        "training_load": round(float(load), 1) if isinstance(load, (int, float)) else None,
        "exercises_sample": exercise_list[:10] if exercise_list else [],
    }


def get_strength_analysis(activity_id: int | None = None, limit: int = 5) -> dict[str, Any]:
    """Get strength training analysis (active sets, reps, volume load, muscle groups, and runner fatigue advice).

    Args:
        activity_id: Specific strength training activity ID to inspect details for (optional).
        limit: Number of recent strength activities to summarize when activity_id is omitted (default: 5, max: 20).
    """
    client = get_client()

    # Case 1: Specific activity ID
    if activity_id is not None:
        try:
            detail = client.connectapi(f"/activity-service/activity/{activity_id}")
            if not isinstance(detail, dict):
                return {"error": f"Strength activity {activity_id} not found"}
            sets_data: dict[str, Any] | None = None
            with suppress(Exception):
                sets_data = client.connectapi(f"/activity-service/activity/{activity_id}/exerciseSets")
            entry = _format_strength_session(detail, sets_data)
            return {"count": 1, "sessions": [entry]}
        except Exception as e:
            return {"error": f"Failed to fetch strength activity {activity_id}: {e}"}

    # Case 2: Recent strength activities list
    effective_limit = max(1, min(20, int(limit)))
    try:
        acts = as_list(client.get_activities(0, 100))
    except Exception as e:
        return {"error": f"Failed to list strength activities: {e}"}

    strength_acts = [a for a in acts if isinstance(a, dict) and _is_strength_activity(a)]
    selected = strength_acts[:effective_limit]

    results: list[dict[str, Any]] = []
    for act in selected:
        act_id = act.get("activityId")
        if not act_id:
            continue
        sets_data = None
        try:
            detail = client.connectapi(f"/activity-service/activity/{act_id}")
            with suppress(Exception):
                sets_data = client.connectapi(f"/activity-service/activity/{act_id}/exerciseSets")
            summary_info = detail if isinstance(detail, dict) else act
            results.append(_format_strength_session(summary_info, sets_data))
        except Exception:
            results.append(_format_strength_session(act, None))

    return {
        "count": len(results),
        "sessions": results,
    }
