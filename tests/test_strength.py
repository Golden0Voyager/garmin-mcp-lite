from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.strength import _classify_exercise_category, get_strength_analysis


class TestClassifyExerciseCategory:
    def test_classifications(self) -> None:
        assert _classify_exercise_category("BARBELL_SQUAT") == "legs_glutes"
        assert _classify_exercise_category("DEADLIFT") == "legs_glutes"
        assert _classify_exercise_category("BENCH_PRESS") == "upper_body"
        assert _classify_exercise_category("PULL_UP") == "upper_body"
        assert _classify_exercise_category("PLANK") == "core"
        assert _classify_exercise_category("SOMETHING_ELSE") == "other"
        assert _classify_exercise_category(None) == "other"


class TestGetStrengthAnalysis:
    def test_get_specific_strength_activity_success(self, mock_get_client: MagicMock) -> None:
        res = get_strength_analysis(activity_id=88002)

        assert res["count"] == 1
        session = res["sessions"][0]
        assert session["id"] == 88002
        assert session["name"] == "Strength Session"
        assert session["active_sets"] == 2
        assert session["rest_sets"] == 1
        assert session["total_reps"] == 22  # 10 + 12
        assert session["total_volume_kg"] == 840.0  # 60kg * 10 + 20kg * 12
        assert session["muscle_group_distribution"]["legs_glutes"] == 1
        assert session["muscle_group_distribution"]["upper_body"] == 1
        assert "下肢与臀腿" in session["runner_fatigue_alert"]
        assert len(session["exercises_sample"]) == 2

    def test_upper_body_only_fatigue_alert(self, mock_get_client: MagicMock) -> None:
        def _fake_connect(path: str) -> dict:
            if path == "/activity-service/activity/88005":
                return {"activityId": 88005, "activityName": "Chest Day"}
            if path == "/activity-service/activity/88005/exerciseSets":
                return {
                    "exerciseSets": [
                        "invalid-set-item",  # non-dict item to cover continue
                        {"setType": "ACTIVE", "duration": 40.0, "repetitionCount": 15, "weight": 50000.0, "exercises": [{"category": "PUSH_UP"}]},
                    ]
                }
            return {}

        mock_get_client.connectapi.side_effect = _fake_connect

        res = get_strength_analysis(activity_id=88005)
        session = res["sessions"][0]
        assert session["muscle_group_distribution"]["legs_glutes"] == 0
        assert "负担较小" in session["runner_fatigue_alert"]

    def test_list_recent_strength_sessions(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities.return_value = [
            {"activityId": 1001, "activityName": "Run", "activityType": {"typeKey": "running"}},
            {"activityId": 88002, "activityName": "Strength Session", "activityType": {"typeKey": "strength_training"}},
            {"activityId": None, "activityType": {"typeKey": "strength_training"}},  # no id, should skip
        ]

        res = get_strength_analysis(limit=2)
        assert res["count"] == 1
        assert res["sessions"][0]["id"] == 88002

    def test_list_strength_detail_exception_fallback(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities.return_value = [
            {"activityId": 88006, "activityName": "Bodyweight Strength", "activityType": {"typeKey": "strength_training"}, "duration": 1500.0, "activeSets": 5},
        ]
        mock_get_client.connectapi.side_effect = RuntimeError("500 detail fail")

        res = get_strength_analysis()
        assert res["count"] == 1
        assert res["sessions"][0]["id"] == 88006
        assert res["sessions"][0]["active_sets"] == 5

    def test_specific_activity_not_found(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.return_value = None
        res = get_strength_analysis(activity_id=99999)
        assert "error" in res

    def test_specific_activity_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = RuntimeError("network down")
        res = get_strength_analysis(activity_id=99999)
        assert "error" in res
        assert "network down" in res["error"]

    def test_list_activities_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities.side_effect = RuntimeError("activities failed")
        res = get_strength_analysis()
        assert "error" in res
        assert "activities failed" in res["error"]
