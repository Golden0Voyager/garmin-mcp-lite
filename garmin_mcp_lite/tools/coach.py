from garmin_mcp_lite.client import get_client


def _summarize_plan(plan_id, detail: dict) -> dict:
    return {
        "id": plan_id,
        "name": detail.get("trainingPlanName"),
        "sport": (detail.get("sportType") or {}).get("sportTypeKey"),
        "status": detail.get("trainingPlanStatus"),
        "start_date": detail.get("startDate"),
        "end_date": detail.get("endDate"),
        "goal": detail.get("trainingPlanGoal"),
    }


def get_coach_plans() -> dict:
    """获取 Garmin Coach 训练计划列表。"""
    client = get_client()

    try:
        plans = client.get_training_plans()
    except Exception as e:
        return {"error": str(e), "plans": []}

    result = []
    for plan in plans or []:
        if isinstance(plan, dict):
            result.append(_summarize_plan(plan.get("trainingPlanId"), plan))
        elif isinstance(plan, str):
            # 可能是 plan ID，尝试获取详情
            try:
                detail = client.get_training_plan_by_id(plan)
                if isinstance(detail, dict):
                    result.append(_summarize_plan(plan, detail))
            except Exception:
                pass

    return {
        "count": len(result),
        "plans": result,
    }
