from __future__ import annotations

from garmin_mcp_lite.tools.training import get_training_plan, get_training_status


class TestGetTrainingPlan:
    def test_returns_workout(self) -> None:
        result = get_training_plan(date="2026-06-19")
        assert result["has_workout"] is True
        assert result["name"] == "Easy Recovery Run"
        assert result["duration_min"] == 45

    def test_no_workout_returns_false(self) -> None:
        result = get_training_plan(date="2026-12-25")
        assert result["has_workout"] is False


class TestGetTrainingStatus:
    def test_returns_status(self) -> None:
        result = get_training_status()
        assert result["training_status"] == "Productive"
        assert result["vo2max"] == 48
        assert result["readiness_score"] == 85
        assert result["recovery_time_h"] == 12.0
