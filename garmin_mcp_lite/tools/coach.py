from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_list


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
        raw_plans = client.get_training_plans()
    except Exception as e:
        return {"error": str(e), "plans": []}

    # Newer garminconnect returns {"trainingPlanList": [...]}; older versions
    # and some endpoints return the list directly.
    plans = as_list(raw_plans.get("trainingPlanList")) if isinstance(raw_plans, dict) else as_list(raw_plans)

    result = []
    for plan in plans:
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
