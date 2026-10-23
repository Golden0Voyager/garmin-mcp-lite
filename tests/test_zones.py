from __future__ import annotations

from unittest.mock import MagicMock, patch

from garmin_mcp_lite.tools.zones import get_zones


class TestZonesClientCompatibility:
    def test_does_not_require_get_heart_rate_zones(self) -> None:
        # garminconnect 0.3.3 (still within the supported range) has no
        # Garmin.get_heart_rate_zones(), so the tool has to read the raw
        # endpoint. A spec'd mock fails loudly if that helper is called again.
        client = MagicMock(spec=["connectapi", "get_lactate_threshold"])
        client.connectapi.return_value = [
            {"zone1Floor": 130, "zone2Floor": 141, "maxHeartRateUsed": 198, "sport": "RUNNING"}
        ]
        client.get_lactate_threshold.return_value = {}

        with patch("garmin_mcp_lite.tools.zones.get_client", return_value=client):
            result = get_zones()

        client.connectapi.assert_called_once_with("/biometric-service/heartRateZones")
        assert result["hr_zones"]["zones"]


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
        mock_get_client.connectapi.side_effect = Exception("boom")
        assert get_zones()["error"] == "boom"

    def test_threshold_failure_does_not_break_zones(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_lactate_threshold.side_effect = Exception("boom")
        result = get_zones()
        assert result["hr_zones"]["zones"]
        assert result["lactate_threshold"]["error"] == "boom"

    def test_ftp_failure_does_not_break_zones(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_cycling_ftp.side_effect = Exception("boom")
        result = get_zones(sport="cycling")
        assert result["hr_zones"]["zones"]
        assert result["ftp"]["error"] == "boom"


class TestZonesPartialConfig:
    def test_missing_zone_floor_is_skipped(self, mock_get_client: MagicMock) -> None:
        # A half-configured zone set must not produce a bogus 0 bpm band.
        mock_get_client.connectapi.side_effect = None
        mock_get_client.connectapi.return_value = [
            {
                "trainingMethod": "HR_MAX",
                "zone1Floor": 120,
                "zone2Floor": 140,
                # zone3Floor missing
                "zone4Floor": 170,
                "zone5Floor": 185,
                "maxHeartRateUsed": 195,
                "sport": "RUNNING",
            }
        ]
        zones = get_zones()["hr_zones"]["zones"]

        assert [z["zone"] for z in zones] == [1, 2, 4, 5]
        # Zone 2 must close at the next *present* floor (zone 4), not at max HR.
        assert zones[1] == {"zone": 2, "label": "aerobic", "min": 140, "max": 169}
        assert zones[3] == {"zone": 5, "label": "anaerobic", "min": 185, "max": 195}

    def test_missing_max_hr_leaves_the_top_zone_open(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = None
        mock_get_client.connectapi.return_value = [
            {"zone1Floor": 120, "zone2Floor": 140, "sport": "RUNNING"}
        ]
        zones = get_zones()["hr_zones"]["zones"]

        assert zones == [
            {"zone": 1, "label": "recovery", "min": 120, "max": 139},
            {"zone": 2, "label": "aerobic", "min": 140, "max": None},
        ]
