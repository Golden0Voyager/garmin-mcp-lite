from __future__ import annotations

from garmin_mcp_lite.tools.hr_trend import get_hr_trend


class TestGetHrTrend:
    def test_returns_hr_data(self) -> None:
        result = get_hr_trend(period="7d")
        assert result["metric"] == "resting"
        assert result["count"] >= 1
        assert result["latest"]["value"] == 48
