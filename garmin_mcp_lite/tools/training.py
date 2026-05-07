from datetime import datetime, timedelta

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import (
    activity_local_date,
    get_first,
    today_str,
)


def get_training_plan(date: str | None = None) -> dict:
    """获取指定日期的训练计划课表。

    Args:
        date: 日期 (YYYY-MM-DD)，默认今天
    """
    client = get_client()
    if not date:
        date = today_str()

    # get_scheduled_workouts 需要 year, month 参数
    year, month = int(date[:4]), int(date[5:7])
    try:
        workouts = client.get_scheduled_workouts(year, month)
    except Exception as e:
        return {
            "date": date,
            "has_workout": False,
            "message": f"获取训练计划失败: {e}",
        }

    # 处理不同返回格式：可能是 dict 列表或字符串列表
    day_workouts = []
    for w in workouts:
        if isinstance(w, dict):
            scheduled = w.get("scheduledDate", "")
        elif isinstance(w, str):
            # 可能是 ID，尝试获取详情
            try:
                detail = client.get_scheduled_workout_by_id(w)
                scheduled = detail.get("scheduledDate", "") if isinstance(detail, dict) else ""
                w = detail if isinstance(detail, dict) else {"workoutId": w}
            except Exception:
                continue
        else:
            continue

        if scheduled.startswith(date):
            day_workouts.append(w)

    if not day_workouts:
        return {
            "date": date,
            "has_workout": False,
            "message": "今日无训练计划",
        }

    workout = day_workouts[0]
    return {
        "date": date,
        "has_workout": True,
        "workout_id": workout.get("workoutId") if isinstance(workout, dict) else str(workout),
        "name": workout.get("workoutName") if isinstance(workout, dict) else None,
        "sport": (
            (workout.get("sportType") or {}).get("sportTypeKey")
            if isinstance(workout, dict)
            else None
        ),
        "description": workout.get("description") if isinstance(workout, dict) else None,
        "duration_min": (
            workout.get("estimatedDuration", 0) // 60
            if isinstance(workout, dict)
            else None
        ),
        "target": _extract_target(workout) if isinstance(workout, dict) else None,
    }


def get_training_status() -> dict:
    """获取当前训练状态摘要。"""
    client = get_client()
    today = today_str()

    # 获取最大摄氧量（用 get_max_metrics API）
    # 尝试多个日期：今天、最近活动日期、更早的日期
    max_metrics = None
    dates_to_try = [today]

    # 从近期活动中补充候选日期，避免额外模块依赖造成重复登录/API 调用
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

    # 解析训练状态
    training_status_raw = get_first(status, "mostRecentTrainingStatus")
    training_status_value = None
    if isinstance(training_status_raw, dict):
        training_status_value = training_status_raw.get("trainingStatus")

    # 解析训练负荷
    load_raw = get_first(status, "mostRecentTrainingLoadBalance")
    load_value = None
    if isinstance(load_raw, dict):
        load_value = load_raw.get("trainingLoad")

    # 获取训练准备度（返回 list，查找最近有数据的日期）
    readiness = {}
    for i in range(7):  # 查最近7天
        check_date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            readiness_list = client.get_training_readiness(check_date)
            if isinstance(readiness_list, list) and readiness_list:
                readiness = readiness_list[0]
                break
        except Exception:
            pass

    return {
        "training_status": training_status_value,
        "vo2max": vo2max_value,
        "load": load_value,
        "recovery_time_h": readiness.get("recoveryTime") if isinstance(readiness, dict) else None,
        "readiness_score": get_first(readiness, "score") if isinstance(readiness, dict) else None,
        "sleep_score": get_first(readiness, "sleepScore") if isinstance(readiness, dict) else None,
        "resting_hr": (
            get_first(readiness, "restingHeartRate")
            if isinstance(readiness, dict)
            else None
        ),
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


def _extract_target(workout: dict) -> dict:
    """从 workout 结构中提取目标配速/心率区间。"""
    steps = workout.get("workoutSteps", [])
    targets = []
    for step in steps:
        target = step.get("targetType", {})
        if target:
            targets.append({
                "step": step.get("stepOrder"),
                "type": target.get("workoutTargetTypeKey"),
                "min": target.get("targetValue"),
                "max": target.get("targetValueHigh"),
                "unit": target.get("targetValueUnit"),
            })
    return {"steps": targets}
