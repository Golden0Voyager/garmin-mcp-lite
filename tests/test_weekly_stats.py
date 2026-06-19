from __future__ import annotations

from garmin_mcp_lite.tools.weekly_stats import get_weekly_stats


class TestGetWeeklyStats:
    def test_returns_stats(self) -> None:
        result = get_weekly_stats(period="week")
        assert result["total_activities"] == 2
        assert result["total_distance_km"] == 30.3
        assert result["total_duration_hours"] == 1.6
