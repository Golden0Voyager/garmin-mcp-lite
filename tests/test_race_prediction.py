from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.race_prediction import get_race_prediction


class TestRacePredictionToday:
    def test_formats_time_and_pace(self) -> None:
        result = get_race_prediction()
        assert result["date"] == "2026-06-18"
        predictions = result["predictions"]
        assert predictions["5k"]["time"] == "21:35"
        assert predictions["5k"]["pace_per_km"] == "04:19"
        assert predictions["half_marathon"]["time"] == "1:44:09"
        assert predictions["marathon"]["time"] == "3:50:19"

    def test_omits_trend_for_today(self) -> None:
        assert "trend" not in get_race_prediction()

    def test_returns_error_when_no_rows(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_race_predictions.side_effect = None
        mock_get_client.get_race_predictions.return_value = []
        assert "error" in get_race_prediction()


class TestRacePredictionTrend:
    def test_reports_change_over_window(self) -> None:
        result = get_race_prediction(period="90d")
        assert result["trend"]["since"] == "2026-04-30"
        # 1295s now vs 1329s a month earlier: negative means faster
        assert result["trend"]["change_s"]["5k"] == -34
        assert result["trend"]["change_s"]["marathon"] == -389

    def test_returns_error_on_empty_window(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_race_predictions.side_effect = None
        mock_get_client.get_race_predictions.return_value = []
        assert "error" in get_race_prediction(period="1y")


class TestRacePredictionErrors:
    def test_returns_error_dict(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_race_predictions.side_effect = Exception("boom")
        assert get_race_prediction()["error"] == "boom"
