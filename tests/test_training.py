from __future__ import annotations

from garmin_mcp_lite.tools.training import get_training_plan, get_training_status


class TestGetTrainingPlan:
    def test_returns_workout(self) -> None:
        result = get_training_plan(date="2026-06-19")
        assert result["has_workout"] is True
        assert result["name"] == "Easy Recovery Run"
        assert result["duration_min"] == 45
        assert result["target"]["steps"][0]["type"] == "pace"
        assert result["target"]["steps"][0]["min"] == 5.5

    def test_ignores_non_dict_workout_steps(self, mock_get_client) -> None:
        mock_get_client.get_workout_by_id.return_value = {
            "workoutName": "Mixed Steps",
            "workoutSegments": [
                {
                    "workoutSteps": [
                        None,
                        {
                            "stepOrder": 1,
                            "targetType": {"workoutTargetTypeKey": "pace"},
                            "targetValueOne": 5.5,
                            "targetValueTwo": 6.5,
                            "targetValueUnit": "min/km",
                        },
                    ]
                }
            ],
        }

        result = get_training_plan(date="2026-06-19")

        assert result["target"]["steps"][0]["min"] == 5.5

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
        assert result["resting_hr"] == 48

    def test_resting_hr_falls_back_to_daily_summary(self, mock_get_client) -> None:
        mock_get_client.get_training_readiness_range.side_effect = Exception("range unavailable")
        mock_get_client.get_training_readiness.return_value = [
            {"score": 85, "recoveryTime": 720, "sleepScore": 82, "calendarDate": "2026-06-18"}
        ]

        result = get_training_status()

        assert result["resting_hr"] == 52

    def test_readiness_exposes_factors(self) -> None:
        readiness = get_training_status()["readiness"]
        assert readiness["score"] == 85
        assert readiness["level"] == "HIGH"
        assert readiness["hrv_weekly_average"] == 52
        assert readiness["factors"]["hrv"] == {"percent": 53, "feedback": "MODERATE"}
        assert readiness["factors"]["recovery_time"] == {"percent": 90, "feedback": "GOOD"}

    def test_readiness_history_is_chronological(self) -> None:
        history = get_training_status()["readiness_history"]
        assert [entry["date"] for entry in history] == ["2026-06-17", "2026-06-18"]
        assert history[-1]["score"] == 85
        assert history[-1]["recovery_time_h"] == 12.0

    def test_acute_load_includes_acwr_detail(self) -> None:
        detail = get_training_status()["acute_load_detail"]
        assert detail["acute"] == 280
        assert detail["chronic"] == 636
        assert detail["ratio"] == 0.9
        assert detail["percent"] == 38
        assert detail["status"] == "OPTIMAL"
        assert detail["chronic_min"] == 508.8
        assert detail["chronic_max"] == 954.0

    def test_four_week_load_includes_targets(self) -> None:
        four_week = get_training_status()["four_week_load"]
        assert four_week["date"] == "2026-06-18"
        assert four_week["feedback"] == "ANAEROBIC_SHORTAGE"
        assert four_week["aerobic_low"] == {"load": 1252, "target_min": 433, "target_max": 952}
        assert four_week["anaerobic"]["target_min"] == 173

    def test_fitness_age_components(self) -> None:
        fitness = get_training_status()["fitness_age"]
        assert fitness["chronological_age"] == 38
        assert fitness["fitness_age"] == 30.1
        assert fitness["achievable_fitness_age"] == 32.6
        assert fitness["components"]["resting_hr"] == 43
        assert fitness["components"]["body_fat"] == 16.5
        assert fitness["components"]["vigorous_days_avg"] == 5.0

    def test_optional_context_failures_do_not_break_status(self, mock_get_client) -> None:
        mock_get_client.get_training_four_week_load_balance.side_effect = Exception("load down")
        mock_get_client.get_fitnessage_data.side_effect = Exception("age down")

        result = get_training_status()

        assert result["four_week_load"] is None
        assert result["fitness_age"] is None
        assert result["readiness"]["score"] == 85
