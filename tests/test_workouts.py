from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.workouts import (
    _pace_to_speed,
    schedule_cycling_workout,
    schedule_running_workout,
)


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


class TestScheduleCyclingWorkout:
    def test_steady_watts_cycling_workout(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"workoutId": 3001, "workoutName": "Z2 Ride"}
        mock_get_client.schedule_workout.return_value = {"workoutScheduleId": 4001}

        res = schedule_cycling_workout(
            name="Z2 Ride",
            date="2026-11-12",
            description="Endurance ride",
            steady_min=45.0,
            target_watts_min=140.0,
            target_watts_max=155.0,
        )

        assert res["ok"] is True
        assert res["workout_id"] == 3001
        assert res["schedule_id"] == 4001
        assert res["steps_count"] == 1

        payload = mock_get_client.upload_workout.call_args[0][0]
        assert payload["sportType"]["sportTypeId"] == 2
        assert payload["sportType"]["sportTypeKey"] == "cycling"

        step = payload["workoutSegments"][0]["workoutSteps"][0]
        assert step["endCondition"]["conditionTypeKey"] == "time"
        assert step["endConditionValue"] == 2700.0  # 45 * 60
        assert step["targetType"]["workoutTargetTypeKey"] == "power.zone"
        assert step["targetValueOne"] == 140.0
        assert step["targetValueTwo"] == 155.0

    def test_cycling_workout_with_ftp_percentage(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_cycling_ftp.return_value = {"functionalThresholdPower": 200.0}
        mock_get_client.upload_workout.return_value = {"workoutId": 3002}
        mock_get_client.schedule_workout.return_value = {"workoutScheduleId": 4002}

        res = schedule_cycling_workout(
            name="FTP Intervals",
            date="2026-11-12",
            warmup_min=10.0,
            warmup_watts=120.0,
            intervals=[
                "invalid-item",  # triggers non-dict continue
                {"duration_min": 5.0, "ftp_pct_min": 95, "ftp_pct_max": 105, "description": "Threshold interval"},
                {"distance_km": 10.0, "description": "Open spin"},  # distance end condition
                {"description": "Lap finish"},  # lap button end condition
            ],
            cooldown_min=5.0,
        )

        assert res["ok"] is True
        assert res["steps_count"] == 5

        payload = mock_get_client.upload_workout.call_args[0][0]
        steps = payload["workoutSegments"][0]["workoutSteps"]
        # Warmup
        assert steps[0]["stepType"]["stepTypeKey"] == "warmup"
        assert steps[0]["targetValueOne"] == 120.0
        assert steps[0]["targetValueTwo"] == 120.0
        # Interval 1 (95% - 105% of 200W = 190W - 210W)
        assert steps[1]["targetValueOne"] == 190.0
        assert steps[1]["targetValueTwo"] == 210.0
        # Interval 2 (distance condition)
        assert steps[2]["endCondition"]["conditionTypeKey"] == "distance"
        assert steps[2]["endConditionValue"] == 10000.0
        # Interval 3 (lap button)
        assert steps[3]["endCondition"]["conditionTypeKey"] == "lap.button"
        # Cooldown
        assert steps[4]["stepType"]["stepTypeKey"] == "cooldown"
        assert steps[4]["endConditionValue"] == 300.0


    def test_cycling_workout_steady_ftp_percentage(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_cycling_ftp.return_value = {"functionalThresholdPower": 200.0}
        mock_get_client.upload_workout.return_value = {"workoutId": 3004}
        mock_get_client.schedule_workout.return_value = {"workoutScheduleId": 4004}

        res = schedule_cycling_workout(
            name="Z2 FTP Ride",
            date="2026-11-12",
            steady_min=30.0,
            target_ftp_pct_min=70.0,
            target_ftp_pct_max=80.0,
        )

        assert res["ok"] is True
        payload = mock_get_client.upload_workout.call_args[0][0]
        step = payload["workoutSegments"][0]["workoutSteps"][0]
        assert step["targetValueOne"] == 140.0
        assert step["targetValueTwo"] == 160.0

    def test_cycling_workout_ftp_exception_fallback(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_cycling_ftp.side_effect = RuntimeError("FTP service unavailable")
        mock_get_client.upload_workout.return_value = {"workoutId": 3006}
        mock_get_client.schedule_workout.return_value = {"workoutScheduleId": 4006}

        res = schedule_cycling_workout(
            name="Ride without FTP",
            date="2026-11-12",
            steady_min=30.0,
            target_ftp_pct_min=70.0,
            target_watts_min=130.0,
            target_watts_max=150.0,
        )
        assert res["ok"] is True
    def test_cycling_single_target_watt(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"workoutId": 3005}
        mock_get_client.schedule_workout.return_value = {"workoutScheduleId": 4005}

        res = schedule_cycling_workout(
            name="Target Watt",
            date="2026-11-12",
            steady_min=20.0,
            target_watts_min=150.0,
        )

        assert res["ok"] is True
        payload = mock_get_client.upload_workout.call_args[0][0]
        step = payload["workoutSegments"][0]["workoutSteps"][0]
        assert step["targetValueOne"] == 142.5  # 150 * 0.95
        assert step["targetValueTwo"] == 157.5  # 150 * 1.05
    def test_cycling_validation_errors(self) -> None:
        assert "error" in schedule_cycling_workout(name="", date="2026-11-12", steady_min=30.0)
        assert "error" in schedule_cycling_workout(name="Ride", date="bad-date", steady_min=30.0)
        assert "error" in schedule_cycling_workout(name="Ride", date="2026-11-12")  # no steps

    def test_cycling_upload_failure(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"error": "upload failed"}
        res = schedule_cycling_workout(name="Ride", date="2026-11-12", steady_min=30.0)
        assert "error" in res

    def test_cycling_schedule_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.upload_workout.return_value = {"workoutId": 3003}
        mock_get_client.schedule_workout.side_effect = RuntimeError("500 schedule")
        res = schedule_cycling_workout(name="Ride", date="2026-11-12", steady_min=30.0)
        assert "error" in res
        assert "500 schedule" in res["error"]
