from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.dive import get_dive_logs


class TestGetDiveLogs:
    def test_get_specific_dive_activity_success(self, mock_get_client: MagicMock) -> None:
        res = get_dive_logs(activity_id=99001)
        assert res["count"] == 1
        dive = res["dives"][0]
        assert dive["id"] == 99001
        assert dive["name"] == "Karangasem Freediving"
        assert dive["type"] == "apnea_diving"
        assert dive["type_name"] == "自由潜水"
        assert dive["max_depth_m"] == 25.4
        assert dive["avg_depth_m"] == 12.3
        assert dive["dive_count"] == 18
        assert dive["bottom_time_min"] == 23.7  # 1420 / 60
        assert dive["max_bottom_time_s"] == 115.0
        assert dive["surface_interval_min"] == 53.3  # 3200 / 60
        assert dive["water_temp_c"] == 28.5
        assert dive["min_hr"] == 48
        assert dive["avg_hr"] == 78
        assert dive["max_hr"] == 95
        assert dive["training_load"] == 12.5

    def test_list_recent_dives(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities.return_value = [
            {
                "activityId": 10001,
                "activityName": "Morning Run",
                "activityType": {"typeKey": "running"},
            },
            {
                "activityId": 10002,
                "activityName": "Scuba Dive",
                "activityType": {"typeKey": "single_gas_diving"},
            },
            {
                "activityId": 99001,
                "activityName": "Karangasem Freediving",
                "activityType": {"typeKey": "apnea_diving"},
            },
        ]

        def _fake_connect(path: str) -> dict:
            if path == "/activity-service/activity/10002":
                return {
                    "activityId": 10002,
                    "activityName": "Scuba Dive",
                    "startTimeLocal": "2026-08-10 10:00:00",
                    "activityType": {"typeKey": "single_gas_diving"},
                    "summaryDTO": {
                        "maxDepth": 18.2,
                        "averageDepth": 11.5,
                        "bottomTime": 2400.0,
                        "averageTemperature": 27.0,
                    },
                }
            if path == "/activity-service/activity/99001":
                return {
                    "activityId": 99001,
                    "activityName": "Karangasem Freediving",
                    "startTimeLocal": "2026-08-18 14:47:19",
                    "activityType": {"typeKey": "apnea_diving"},
                    "summaryDTO": {
                        "maxDepth": 25.4,
                        "averageDepth": 12.3,
                        "diveCount": 18,
                        "bottomTime": 1420.0,
                    },
                }
            return {}

        mock_get_client.connectapi.side_effect = _fake_connect

        res = get_dive_logs(limit=2)
        # Running activity filtered out, only 2 dive activities returned
        assert res["count"] == 2
        assert res["dives"][0]["id"] == 10002
        assert res["dives"][0]["type_name"] == "单气水肺潜水"
        assert res["dives"][0]["max_depth_m"] == 18.2
        assert res["dives"][1]["id"] == 99001
        assert res["dives"][1]["type_name"] == "自由潜水"

    def test_specific_dive_not_found(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.return_value = None
        res = get_dive_logs(activity_id=123456)
        assert "error" in res

    def test_specific_dive_api_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = RuntimeError("dive service error")
        res = get_dive_logs(activity_id=123456)
        assert "error" in res
        assert "dive service error" in res["error"]

    def test_list_dives_api_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities.side_effect = RuntimeError("activities failed")
        res = get_dive_logs()
        assert "error" in res
        assert "activities failed" in res["error"]
