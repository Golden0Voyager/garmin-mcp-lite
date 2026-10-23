from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.zones import get_zones


class TestZonesRunning:
    def test_builds_explicit_zone_ranges(self) -> None:
        result = get_zones()
        assert result["sport"] == "RUNNING"
        zones = result["hr_zones"]["zones"]
        assert len(zones) == 5
        assert zones[0] == {"zone": 1, "label": "recovery", "min": 130, "max": 140}
        # the top zone is open-ended and closes at max HR
        assert zones[4] == {"zone": 5, "label": "anaerobic", "min": 183, "max": 198}

    def test_reports_zone_anchors(self) -> None:
        hr_zones = get_zones()["hr_zones"]
        assert hr_zones["method"] == "HR_RESERVE"
        assert hr_zones["max_hr"] == 198
        assert hr_zones["resting_hr"] == 43
        assert hr_zones["lthr"] == 166

    def test_includes_lactate_threshold(self) -> None:
        lt = get_zones()["lactate_threshold"]
        assert lt["heart_rate"] == 166
        assert lt["running_power_w"] == 404
        assert lt["stale"] is True
        # no threshold speed recorded, so no pace can be derived
        assert lt["pace_per_km"] is None


class TestZonesCycling:
    def test_includes_ftp_without_running_thresholds(self) -> None:
        result = get_zones(sport="cycling")
        assert result["sport"] == "CYCLING"
        assert result["ftp"]["watts"] == 194
        assert result["ftp"]["date"] == "2025-07-30"
        assert result["ftp"]["stale"] is True
        assert "lactate_threshold" not in result


class TestZonesMissingConfig:
    def test_reports_missing_zones_for_sport(self) -> None:
        result = get_zones(sport="swimming")
        assert "error" in result["hr_zones"]
        assert "zones" not in result["hr_zones"]


class TestZonesErrors:
    def test_returns_error_dict(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_heart_rate_zones.side_effect = Exception("boom")
        assert get_zones()["error"] == "boom"

    def test_threshold_failure_does_not_break_zones(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_lactate_threshold.side_effect = Exception("boom")
        result = get_zones()
        assert result["hr_zones"]["zones"]
        assert result["lactate_threshold"]["error"] == "boom"
