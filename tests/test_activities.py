from __future__ import annotations

from garmin_mcp_lite.tools.activities import get_activity_detail, list_activities


class TestListActivities:
    def test_returns_activities(self) -> None:
        result = list_activities()
        assert result["count"] == 2
        assert len(result["activities"]) == 2
        assert result["activities"][0]["name"] == "Morning Run"

    def test_filters_by_type(self) -> None:
        result = list_activities(activity_type="running")
        assert result["count"] == 1
        assert result["activities"][0]["type"] == "running"

    def test_respects_limit(self) -> None:
        result = list_activities(limit=1)
        assert result["count"] == 1


class TestGetActivityDetail:
    def test_returns_summary(self) -> None:
        result = get_activity_detail(12345)
        assert result["id"] == 12345
        assert result["name"] == "Morning Run"
        assert result["date"] == "2026-06-18 07:30:00"
        assert result["distance_km"] == 5.23
        assert result["elevation_gain_m"] == 35.0

    def test_accepts_optional_fields(self) -> None:
        result = get_activity_detail(12345, fields=["splits"])
        assert "splits" in result

    def test_includes_laps_when_requested(self) -> None:
        result = get_activity_detail(12345, fields=["laps"])
        assert result["laps"]["lapDTOs"][0]["lapIndex"] == 1

    def test_includes_training_load_by_default(self) -> None:
        result = get_activity_detail(12345)
        assert result["training_load"] == 77.4
        assert result["training_effect"]["aerobic"] == 3.0
        assert result["training_effect"]["aerobic_label"] == "AEROBIC_BASE"
        assert result["training_effect"]["anaerobic"] == 0.0

    def test_includes_weather_and_gear_when_requested(self) -> None:
        result = get_activity_detail(12345, fields=["weather", "gear"])
        assert result["weather"]["available"] is True
        assert result["weather"]["temp_c"] == 26.0
        assert result["weather"]["humidity"] == 61.0
        assert result["weather"]["condition"] == "Partly Cloudy"
        assert result["gear"][0]["name"] == "Strong Wind 3.0 TR"
        assert result["gear"][0]["distance_used_km"] == 461.66

    def test_includes_typed_splits_when_requested(self) -> None:
        result = get_activity_detail(12345, fields=["typedSplits"])
        assert result["typed_splits"]["splits"][0]["type"] == "INTERVAL_ACTIVE"

    def test_optional_sections_isolate_upstream_errors(self, mock_get_client) -> None:
        mock_get_client.get_activity_weather.side_effect = Exception("weather down")
        mock_get_client.get_activity_gear_v2.side_effect = Exception("gear down")
        mock_get_client.get_activity_typed_splits.side_effect = Exception("splits down")

        result = get_activity_detail(12345, fields=["weather", "gear", "typedSplits"])

        assert result["weather"]["error"] == "weather down"
        assert result["gear"]["error"] == "gear down"
        assert result["typed_splits"]["error"] == "splits down"
