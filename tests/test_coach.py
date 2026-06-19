from __future__ import annotations

from garmin_mcp_lite.tools.coach import get_coach_plans


class TestGetCoachPlans:
    def test_returns_plans(self) -> None:
        result = get_coach_plans()
        assert result["count"] == 1
        plan = result["plans"][0]
        assert plan["name"] == "Half Marathon Plan"
        assert plan["sport"] == "running"
        assert plan["status"] == "ACTIVE"
