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
    """List active Garmin Coach training plans."""
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
            # May be a plan ID — attempt to fetch details
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
