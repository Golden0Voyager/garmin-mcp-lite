from __future__ import annotations

from garmin_mcp_lite.tools.health import get_health_data


class TestGetHealthData:
    def test_returns_sleep(self) -> None:
        result = get_health_data(metric="sleep")
        assert result["sleep"]["score"] == 78
        assert result["sleep"]["duration_min"] == 420

    def test_returns_hrv(self) -> None:
        result = get_health_data(metric="hrv")
        assert result["hrv"]["weekly_avg"] == 52.3
        assert result["hrv"]["status"] == "BALANCED"

    def test_returns_stress(self) -> None:
        result = get_health_data(metric="stress")
        assert result["stress"]["avg_level"] == 35

    def test_returns_body_battery(self) -> None:
        result = get_health_data(metric="body_battery")
        assert result["body_battery"]["last_level"] == 65

    def test_returns_spo2(self) -> None:
        result = get_health_data(metric="spo2")
        assert result["spo2"]["avg"] == 97.0

    def test_returns_respiration(self) -> None:
        result = get_health_data(metric="respiration")
        assert result["respiration"]["avg"] == 14.2

    def test_returns_intensity(self) -> None:
        result = get_health_data(metric="intensity")
        assert result["intensity"]["weekly_total"] == 320

    def test_returns_steps(self) -> None:
        result = get_health_data(metric="steps")
        assert result["daily_summary"]["steps"] == 8542

    def test_returns_all(self) -> None:
        result = get_health_data(metric="all")
        assert "sleep" in result
        assert "hrv" in result
        assert "stress" in result
        assert "body_battery" in result
