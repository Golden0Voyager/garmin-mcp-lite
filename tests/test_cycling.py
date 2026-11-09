from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.cycling import get_cycling_power


class TestGetCyclingPower:
    def test_get_specific_cycling_activity_success(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_cycling_ftp.return_value = {
            "functionalThresholdPower": 200,
            "calendarDate": "2026-08-01",
        }
        mock_get_client.get_user_summary.return_value = {"weight": 70000.0}  # 70 kg

        res = get_cycling_power(activity_id=88001)

        assert res["count"] == 1
        assert res["ftp"]["ftp_watts"] == 200
        assert res["ftp"]["ftp_date"] == "2026-08-01"
        assert res["ftp"]["w_per_kg"] == 2.86  # 200 / 70

        ride = res["rides"][0]
        assert ride["id"] == 88001
        assert ride["name"] == "Road Cycling"
        assert ride["avg_power_watts"] == 165
        assert ride["max_power_watts"] == 320
        assert ride["normalized_power_watts"] == 178
        assert ride["training_stress_score"] == 68.5
        assert ride["intensity_factor"] == 0.92
        assert ride["avg_cadence"] == 85
        assert ride["duration_min"] == 60.0
        assert ride["distance_km"] == 30.0

    def test_list_recent_rides(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities.return_value = [
            {"activityId": 1001, "activityName": "Run", "activityType": {"typeKey": "running"}},
            {"activityId": 88001, "activityName": "Road Cycling", "activityType": {"typeKey": "cycling"}},
            {"activityId": None, "activityType": {"typeKey": "cycling"}},  # no id, should skip
        ]

        res = get_cycling_power(limit=2)
        assert res["count"] == 1
        assert res["rides"][0]["id"] == 88001

    def test_list_rides_detail_exception_fallback(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities.return_value = [
            {"activityId": 88003, "activityName": "Gravel", "activityType": {"typeKey": "indoor_cycling"}, "duration": 1800.0},
        ]
        mock_get_client.connectapi.side_effect = RuntimeError("500 detail fail")

        res = get_cycling_power()
        assert res["count"] == 1
        assert res["rides"][0]["id"] == 88003

    def test_specific_activity_not_found(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.return_value = None
        res = get_cycling_power(activity_id=99999)
        assert "error" in res

    def test_specific_activity_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = RuntimeError("network down")
        res = get_cycling_power(activity_id=99999)
        assert "error" in res
        assert "network down" in res["error"]

    def test_list_activities_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities.side_effect = RuntimeError("activities failed")
        res = get_cycling_power()
        assert "error" in res
        assert "activities failed" in res["error"]
