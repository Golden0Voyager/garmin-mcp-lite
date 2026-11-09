from __future__ import annotations

from datetime import date
from typing import Any

from garmin_mcp_lite.client import get_client


def _event_day(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw or "")[:10])
    except ValueError:
        return None


def _pace_to_speed(pace_str: str | None) -> float | None:
    """Convert pace string 'MM:SS' or 'M:SS' to speed in meters per second (m/s)."""
    if not pace_str or not isinstance(pace_str, str):
        return None
    parts = [p.strip() for p in pace_str.split(":") if p.strip()]
    try:
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            total_seconds = m * 60 + s
            if total_seconds <= 0:
                return None
            return round(1000.0 / total_seconds, 3)
    except ValueError:
        return None
    return None


def _build_step(
    step_order: int,
    step_type_key: str,
    distance_km: float | None = None,
    duration_seconds: float | None = None,
    pace_min: str | None = None,
    pace_max: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    """Build a single ExecutableStepDTO for Garmin workout."""
    step_type_ids = {
        "warmup": (1, "warmup", 1),
        "cooldown": (2, "cooldown", 2),
        "interval": (3, "interval", 3),
        "recovery": (4, "recovery", 4),
    }
    type_id, type_key, display_order = step_type_ids.get(step_type_key, (3, "interval", 3))

    step: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": {
            "stepTypeId": type_id,
            "stepTypeKey": type_key,
            "displayOrder": display_order,
        },
        "description": description or "",
    }

    # Condition: distance or time
    if distance_km is not None and distance_km > 0:
        step["endCondition"] = {
            "conditionTypeId": 1,
            "conditionTypeKey": "distance",
            "displayOrder": 1,
            "displayable": True,
        }
        step["endConditionValue"] = round(float(distance_km) * 1000.0, 1)
    elif duration_seconds is not None and duration_seconds > 0:
        step["endCondition"] = {
            "conditionTypeId": 2,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        }
        step["endConditionValue"] = round(float(duration_seconds), 1)
    else:
        # Default fallback: lap button press
        step["endCondition"] = {
            "conditionTypeId": 3,
            "conditionTypeKey": "lap.button",
            "displayOrder": 3,
            "displayable": True,
        }
        step["endConditionValue"] = 1.0

    # Target: pace zone or no target
    speed_fast = _pace_to_speed(pace_min)
    speed_slow = _pace_to_speed(pace_max)

    if speed_fast is not None and speed_slow is not None:
        # In Garmin pace zones, targetValueOne is faster speed (higher m/s), targetValueTwo is slower
        v_one = max(speed_fast, speed_slow)
        v_two = min(speed_fast, speed_slow)
        step["targetType"] = {
            "workoutTargetTypeId": 6,
            "workoutTargetTypeKey": "pace.zone",
            "displayOrder": 6,
        }
        step["targetValueOne"] = v_one
        step["targetValueTwo"] = v_two
    else:
        step["targetType"] = {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        }

    return step


def schedule_running_workout(
    name: str,
    date: str,
    description: str = "",
    steady_km: float | None = None,
    pace_min: str | None = None,
    pace_max: str | None = None,
    warmup_km: float | None = None,
    warmup_pace_min: str | None = None,
    warmup_pace_max: str | None = None,
    intervals: list[dict[str, Any]] | None = None,
    cooldown_km: float | None = None,
    cooldown_pace_min: str | None = None,
    cooldown_pace_max: str | None = None,
) -> dict[str, Any]:
    """Create a structured running workout and schedule it to Garmin Connect calendar.

    Args:
        name: Workout name (e.g. 'W1D2-E有氧跑10K').
        date: Schedule date in YYYY-MM-DD format.
        description: Description of the workout.
        steady_km: Distance in km for a simple steady run (e.g. 10.0).
        pace_min: Faster pace bound (e.g. '5:20').
        pace_max: Slower pace bound (e.g. '5:35').
        warmup_km: Warmup distance in km (optional).
        warmup_pace_min: Warmup faster pace bound (optional).
        warmup_pace_max: Warmup slower pace bound (optional).
        intervals: List of interval dicts, each with keys like:
                   {'distance_km': 6.0, 'pace_min': '4:25', 'pace_max': '4:30', 'description': 'Tempo'}
                   or {'duration_min': 30.0, ...}.
        cooldown_km: Cooldown distance in km (optional).
        cooldown_pace_min: Cooldown faster pace bound (optional).
        cooldown_pace_max: Cooldown slower pace bound (optional).
    """
    if not name or not str(name).strip():
        return {"error": "Workout name must not be blank"}
    if not date or not _event_day(date):
        return {"error": "Invalid date format, expected YYYY-MM-DD"}

    steps: list[dict[str, Any]] = []
    order = 1

    # 1. Warmup
    if warmup_km is not None and warmup_km > 0:
        steps.append(
            _build_step(
                step_order=order,
                step_type_key="warmup",
                distance_km=warmup_km,
                pace_min=warmup_pace_min,
                pace_max=warmup_pace_max,
                description="慢跑热身",
            )
        )
        order += 1

    # 2. Intervals or Steady run
    if intervals and isinstance(intervals, list):
        for item in intervals:
            if not isinstance(item, dict):
                continue
            dist = item.get("distance_km")
            dur_min = item.get("duration_min")
            dur_sec = float(dur_min) * 60.0 if dur_min is not None else None
            p_min = item.get("pace_min") or pace_min
            p_max = item.get("pace_max") or pace_max
            desc = item.get("description", "")
            step_type = item.get("step_type", "interval")
            steps.append(
                _build_step(
                    step_order=order,
                    step_type_key=step_type,
                    distance_km=float(dist) if dist is not None else None,
                    duration_seconds=dur_sec,
                    pace_min=p_min,
                    pace_max=p_max,
                    description=desc,
                )
            )
            order += 1
    elif steady_km is not None and steady_km > 0:
        steps.append(
            _build_step(
                step_order=order,
                step_type_key="interval",
                distance_km=steady_km,
                pace_min=pace_min,
                pace_max=pace_max,
                description="匀速跑步",
            )
        )
        order += 1

    # 3. Cooldown
    if cooldown_km is not None and cooldown_km > 0:
        steps.append(
            _build_step(
                step_order=order,
                step_type_key="cooldown",
                distance_km=cooldown_km,
                pace_min=cooldown_pace_min,
                pace_max=cooldown_pace_max,
                description="慢跑冷身",
            )
        )
        order += 1

    if not steps:
        return {"error": "Workout must contain at least one step (specify steady_km, intervals, or warmup/cooldown)"}

    workout_payload: dict[str, Any] = {
        "workoutName": str(name).strip(),
        "description": str(description or "").strip(),
        "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                "workoutSteps": steps,
            }
        ],
    }

    client = get_client()
    try:
        upload_resp = client.upload_workout(workout_payload)
        workout_id = upload_resp.get("workoutId") if isinstance(upload_resp, dict) else None
        if not workout_id:
            return {"error": f"Failed to upload workout: {upload_resp}"}

        sched_resp = client.schedule_workout(workout_id, date[:10])
        sched_id = sched_resp.get("workoutScheduleId") if isinstance(sched_resp, dict) else None

        return {
            "ok": True,
            "workout_id": workout_id,
            "schedule_id": sched_id,
            "name": name,
            "date": date[:10],
            "steps_count": len(steps),
        }
    except Exception as e:
        return {"error": f"Failed to schedule workout: {e}"}
