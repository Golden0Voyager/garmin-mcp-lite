from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.hrv import get_hrv_status


class TestGetHrvStatus:
    def test_get_hrv_status_success(self, mock_get_client: MagicMock) -> None:
        res = get_hrv_status("2026-11-08")
        assert res["date"] == "2026-11-08"
        assert res["status"] == "BALANCED"
        assert res["weekly_avg_ms"] == 52.3
        assert res["last_night_avg_ms"] == 48.0
        assert res["last_night_5min_high_ms"] == 64
        assert res["baseline"]["balanced_low"] == 50
        assert res["baseline"]["balanced_upper"] == 66
        assert res["baseline"]["range_ms"] == "50 - 66 ms"
        assert "良好" in res["training_guidance"]
        assert res["readings_sample_count"] == 1

    def test_hrv_status_balanced_guidance(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {
                "calendarDate": "2026-11-07",
                "weeklyAvg": 55,
                "lastNightAvg": 58,
                "baseline": {"balancedLow": 50, "balancedUpper": 66},
                "status": "BALANCED",
            }
        }
        res = get_hrv_status("2026-11-07")
        assert res["status"] == "BALANCED"
        assert "良好" in res["training_guidance"]

    def test_hrv_status_unbalanced_guidance(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {
                "calendarDate": "2026-11-08",
                "weeklyAvg": 48,
                "lastNightAvg": 44,
                "baseline": {"balancedLow": 50, "balancedUpper": 66},
                "status": "UNBALANCED",
            }
        }
        res = get_hrv_status("2026-11-08")
        assert res["status"] == "UNBALANCED"
        assert "累积疲劳" in res["training_guidance"]

    def test_hrv_status_building_guidance(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {
                "calendarDate": "2026-11-04",
                "weeklyAvg": None,
                "lastNightAvg": 40,
                "status": "NONE",
            }
        }
        res = get_hrv_status("2026-11-04")
        assert "基线建立中" in res["training_guidance"]
    def test_hrv_status_low_guidance(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {
                "calendarDate": "2026-11-06",
                "weeklyAvg": 45,
                "lastNightAvg": 35,
                "baseline": {"balancedLow": 50, "balancedUpper": 66},
                "status": "LOW",
            }
        }
        res = get_hrv_status("2026-11-06")
        assert res["status"] == "LOW"
        assert "疲劳" in res["training_guidance"]

    def test_hrv_no_summary_data(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {}
        res = get_hrv_status("2026-11-05")
        assert res["status"] == "NO_DATA"

    def test_hrv_none_response(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = None
        res = get_hrv_status("2026-11-05")
        assert res["status"] == "NO_DATA"

    def test_hrv_api_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.side_effect = RuntimeError("network timeout")
        res = get_hrv_status("2026-11-08")
        assert "error" in res
        assert "network timeout" in res["error"]
