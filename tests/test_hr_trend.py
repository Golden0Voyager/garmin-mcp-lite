from __future__ import annotations

from garmin_mcp_lite.tools.hr_trend import get_hr_trend


class TestGetHrTrend:
    def test_returns_hr_data(self) -> None:
        result = get_hr_trend(period="7d")
        assert result["metric"] == "resting"
        assert result["count"] >= 1
        assert result["latest"]["value"] == 48

    def test_uses_bulk_rhr_endpoint(self, mock_get_client) -> None:
        result = get_hr_trend(period="7d")

        mock_get_client.get_rhr_daily.assert_called_once()
        mock_get_client.get_training_readiness.assert_not_called()
        assert result["series"] == [
            {"date": "2026-06-17", "value": 50},
            {"date": "2026-06-18", "value": 48},
        ]

    def test_falls_back_to_daily_scan(self, mock_get_client) -> None:
        mock_get_client.get_rhr_daily.side_effect = Exception("bulk unavailable")

        result = get_hr_trend(period="7d")

        assert result["latest"]["value"] == 48
        assert result["series"][-1] == {"date": result["latest"]["date"], "value": 48}
