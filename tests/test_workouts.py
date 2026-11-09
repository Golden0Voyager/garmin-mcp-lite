from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.workouts import _pace_to_speed, schedule_running_workout


class TestPaceToSpeed:
    def test_valid_paces(self) -> None:
        # 5:00 /km -> 1000 / 300 = 3.333 m/s
        assert _pace_to_speed("5:00") == 3.333
        # 4:10 /km -> 1000 / 250 = 4.0 m/s
        assert _pace_to_speed("04:10") == 4.0
        # 3:20 /km -> 1000 / 200 = 5.0 m/s
        assert _pace_to_speed("3:20") == 5.0

    def test_invalid_paces(self) -> None:
        assert _pace_to_speed("") is None
        assert _pace_to_speed("abc") is None
        assert _pace_to_speed("a:b") is None
        assert _pace_to_speed("0:00") is None
        assert _pace_to_speed("1:2:3") is None
        assert _pace_to_speed(None) is None


class TestScheduleRunningWorkout:
    def test_steady_run_upload_and_schedule_success(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"workoutId": 1001, "workoutName": "E 10K"}
        mock_get_client.schedule_workout.return_value = {"workoutScheduleId": 2001}

        res = schedule_running_workout(
            name="E 10K",
            date="2026-11-10",
            description="Easy run",
            steady_km=10.0,
            pace_min="5:20",
            pace_max="5:35",
        )

        assert res["ok"] is True
        assert res["workout_id"] == 1001
        assert res["schedule_id"] == 2001
        assert res["steps_count"] == 1

        mock_get_client.upload_workout.assert_called_once()
        payload = mock_get_client.upload_workout.call_args[0][0]
        assert payload["workoutName"] == "E 10K"
        assert payload["sportType"]["sportTypeKey"] == "running"

        steps = payload["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 1
        step = steps[0]
        assert step["stepType"]["stepTypeKey"] == "interval"
        assert step["endCondition"]["conditionTypeKey"] == "distance"
        assert step["endConditionValue"] == 10000.0
        assert step["targetType"]["workoutTargetTypeKey"] == "pace.zone"
        # 5:20 is ~3.125 m/s, 5:35 is ~2.985 m/s
        assert step["targetValueOne"] == 3.125
        assert step["targetValueTwo"] == 2.985

        mock_get_client.schedule_workout.assert_called_once_with(1001, "2026-11-10")

    def test_interval_with_warmup_and_cooldown(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"workoutId": 1002}
        mock_get_client.schedule_workout.return_value = {"workoutScheduleId": 2002}

        res = schedule_running_workout(
            name="Tempo 10K",
            date="2026-11-11",
            warmup_km=2.0,
            warmup_pace_min="5:30",
            warmup_pace_max="6:00",
            intervals=[
                {
                    "distance_km": 6.0,
                    "pace_min": "4:25",
                    "pace_max": "4:30",
                    "description": "Tempo block",
                }
            ],
            cooldown_km=2.0,
            cooldown_pace_min="5:30",
            cooldown_pace_max="6:00",
        )

        assert res["ok"] is True
        assert res["steps_count"] == 3

        payload = mock_get_client.upload_workout.call_args[0][0]
        steps = payload["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 3

        assert steps[0]["stepType"]["stepTypeKey"] == "warmup"
        assert steps[0]["endConditionValue"] == 2000.0

        assert steps[1]["stepType"]["stepTypeKey"] == "interval"
        assert steps[1]["endConditionValue"] == 6000.0
        assert steps[1]["description"] == "Tempo block"
        assert steps[1]["targetValueOne"] == 3.774
        assert steps[1]["targetValueTwo"] == 3.704

        assert steps[2]["stepType"]["stepTypeKey"] == "cooldown"
        assert steps[2]["endConditionValue"] == 2000.0

    def test_duration_and_lap_button_intervals(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"workoutId": 1004}
        mock_get_client.schedule_workout.return_value = {"workoutScheduleId": 2004}

        res = schedule_running_workout(
            name="Mixed Intervals",
            date="2026-11-10",
            intervals=[
                "not-a-dict",  # triggers continue on non-dict
                {"duration_min": 15.0, "pace_min": "5:00", "pace_max": "5:30"},
                {"description": "Open lap run"},  # triggers lap button fallback
            ],
        )

        assert res["ok"] is True
        assert res["steps_count"] == 2
        payload = mock_get_client.upload_workout.call_args[0][0]
        steps = payload["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["endCondition"]["conditionTypeKey"] == "time"
        assert steps[0]["endConditionValue"] == 900.0
        assert steps[1]["endCondition"]["conditionTypeKey"] == "lap.button"
        assert steps[1]["endConditionValue"] == 1.0

    def test_validation_errors(self) -> None:
        assert "error" in schedule_running_workout(name="", date="2026-11-10", steady_km=5.0)
        assert "error" in schedule_running_workout(name="Run", date="bad-date", steady_km=5.0)
        assert "error" in schedule_running_workout(name="Run", date="2026-11-10")  # no steps

    def test_upload_failure_returns_error(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"error": "quota exceeded"}
        res = schedule_running_workout(name="Run", date="2026-11-10", steady_km=5.0)
        assert "error" in res

    def test_schedule_exception_returns_error(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"workoutId": 1003}
        mock_get_client.schedule_workout.side_effect = RuntimeError("schedule endpoint 500")
        res = schedule_running_workout(name="Run", date="2026-11-10", steady_km=5.0)
        assert "error" in res
        assert "schedule endpoint 500" in res["error"]
