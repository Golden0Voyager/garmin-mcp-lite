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
        assert result["distance_km"] == 5.23
        assert result["elevation_gain_m"] == 35.0

    def test_accepts_optional_fields(self) -> None:
        result = get_activity_detail(12345, fields=["splits"])
        assert "splits" in result
