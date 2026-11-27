from __future__ import annotations

from garmin_mcp_lite.tools.health import get_health_data


class TestGetHealthData:
    def test_returns_sleep(self) -> None:
        result = get_health_data(metric="sleep")
        assert result["sleep"]["score"] == 78
        assert result["sleep"]["duration_min"] == 420

    def test_sleep_includes_detailed_recovery_context(self) -> None:
        sleep = get_health_data(metric="sleep")["sleep"]
        assert sleep["score_quality"] == "FAIR"
        assert sleep["light_min"] == 200
        assert sleep["rem_min"] == 105
        assert sleep["awake_min"] == 21
        assert sleep["avg_spo2"] == 96.0
        assert sleep["avg_stress"] == 18
        assert sleep["avg_overnight_hrv"] == 52.0
        assert sleep["restless_moments"] == 6
        assert sleep["sleep_start_local"] == "2026-06-17T23:00:00.0"
        assert sleep["score_components"]["deepPercentage"] == {
            "value": 22,
            "qualifier": "EXCELLENT",
        }

    def test_sleep_prefers_explicit_minute_fields(self, mock_get_client) -> None:
        mock_get_client.get_sleep_data.return_value["dailySleepDTO"]["sleepTimeInMinutes"] = 420

        result = get_health_data(metric="sleep")

        assert result["sleep"]["duration_min"] == 420

    def test_lifestyle_reports_upstream_errors(self, mock_get_client) -> None:
        mock_get_client.get_lifestyle_logging_data.side_effect = Exception("boom")

        result = get_health_data(metric="lifestyle")

        assert result["lifestyle"]["error"] == "boom"

    def test_returns_lifestyle(self) -> None:
        lifestyle = get_health_data(metric="lifestyle", date="2026-11-27")["lifestyle"]
        assert lifestyle["tracked"] == 15
        assert lifestyle["completed"] == 1
        assert lifestyle["items"][2] == {
            "name": "Screens Before Bed",
            "category": "SLEEP_RELATED",
            "measurement_type": "NONE",
            "sleep_related": True,
        }
        assert len(lifestyle["completion_stats"]) == 2

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
        assert "lifestyle" in result
