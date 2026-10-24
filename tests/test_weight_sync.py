"""Tests for the Xiaomi -> Garmin weight sync.

The behaviour that matters is what it refuses to do: write a day Garmin already
has, write twice for one day, or write anything at all when the Xiaomi token is
missing. Those are the cases a user cannot easily undo.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from garmin_mcp_lite.tools import weight_sync
from garmin_mcp_lite.xiaomi import XiaomiError


def _record(day: str, weight: float = 71.2, **extra) -> dict:
    return {"date": day, "timestamp": f"{day}T07:00:00", "weight_kg": weight, "source": "yunmai", **extra}


@pytest.fixture()
def mocks():
    with (
        patch.object(weight_sync, "fetch_weights") as fetch,
        patch.object(weight_sync, "get_body_composition") as read,
        patch.object(weight_sync, "add_body_composition") as write,
    ):
        read.return_value = {"count": 0, "records": []}
        write.return_value = {"written": True, "verified": True}
        yield fetch, read, write


class TestPreconditions:
    def test_missing_token_is_reported_with_the_login_command(self, mocks) -> None:
        fetch, read, write = mocks
        fetch.side_effect = XiaomiError("No Mi Fitness token at /x. Run `garmin-mcp-lite-xiaomi-login` once")

        result = weight_sync.sync_weight()

        assert "garmin-mcp-lite-xiaomi-login" in result["error"]
        assert result["written"] == []
        read.assert_not_called()
        write.assert_not_called()

    def test_network_failure_is_reported(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.side_effect = ConnectionError("dns died")

        result = weight_sync.sync_weight()

        assert "dns died" in result["error"]
        write.assert_not_called()

    def test_garmin_read_failure_aborts_before_writing(self, mocks) -> None:
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20")]
        read.return_value = {"error": "401"}

        result = weight_sync.sync_weight()

        assert "401" in result["error"]
        # Without knowing what Garmin already has, writing would duplicate.
        write.assert_not_called()


class TestDryRun:
    def test_reports_without_writing(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20"), _record("2026-10-21")]

        result = weight_sync.sync_weight(days=7, dry_run=True)

        assert result["dry_run"] is True
        assert [item["date"] for item in result["written"]] == ["2026-10-20", "2026-10-21"]
        assert all(item["would_write"] for item in result["written"])
        write.assert_not_called()


class TestDeduplication:
    def test_skips_days_garmin_already_has(self, mocks) -> None:
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20", 71.0), _record("2026-10-21", 71.2)]
        read.return_value = {"records": [{"date": "2026-10-20", "weight_kg": 71.0}]}

        result = weight_sync.sync_weight()

        assert [item["date"] for item in result["written"]] == ["2026-10-21"]
        assert [item["date"] for item in result["skipped"]] == ["2026-10-20"]
        assert result["garmin"]["days_already_present"] == 1
        write.assert_called_once()

    def test_is_idempotent(self, mocks) -> None:
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20")]
        read.return_value = {"records": [{"date": "2026-10-20", "weight_kg": 71.2}]}

        result = weight_sync.sync_weight()

        assert result["written"] == []
        assert len(result["skipped"]) == 1
        write.assert_not_called()

    def test_keeps_only_the_earliest_weigh_in_of_a_day(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [
            {"date": "2026-10-20", "timestamp": "2026-10-20T21:30:00", "weight_kg": 72.4, "source": "x"},
            {"date": "2026-10-20", "timestamp": "2026-10-20T06:45:00", "weight_kg": 71.2, "source": "x"},
            {"date": "2026-10-20", "timestamp": "2026-10-20T12:00:00", "weight_kg": 71.8, "source": "x"},
        ]

        result = weight_sync.sync_weight()

        # Morning, fasted weight is the one a trend line is about.
        assert result["written"][0]["weight_kg"] == 71.2
        assert result["xiaomi"]["same_day_collapsed"] == 2
        assert write.call_count == 1


class TestWriting:
    def test_forwards_every_measured_field(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [
            _record(
                "2026-10-20",
                71.2,
                body_fat_pct=18.4,
                body_water_pct=55.2,
                muscle_mass_kg=28.5,
                bone_mass_kg=3.1,
                bmi=22.9,
                basal_met=1600,
                metabolic_age=36.5,
            )
        ]

        weight_sync.sync_weight()

        kwargs = write.call_args.kwargs
        assert kwargs["weight"] == 71.2
        assert kwargs["date"] == "2026-10-20T07:00:00"
        assert kwargs["body_fat"] == 18.4
        assert kwargs["body_water"] == 55.2
        assert kwargs["muscle_mass"] == 28.5
        assert kwargs["bone_mass"] == 3.1
        assert kwargs["bmi"] == 22.9
        assert kwargs["basal_met"] == 1600
        # metabolic_age must be an int: Garmin's FIT field has no decimals.
        assert kwargs["metabolic_age"] == 36

    def test_omits_metrics_the_scale_did_not_measure(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]

        weight_sync.sync_weight()

        kwargs = write.call_args.kwargs
        assert kwargs["body_fat"] is None
        assert kwargs["metabolic_age"] is None

    def test_records_a_failed_write(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]
        write.return_value = {"error": "upload refused", "written": False}

        result = weight_sync.sync_weight()

        assert result["written"] == []
        assert result["failed"] == [{"date": "2026-10-20", "error": "upload refused"}]

    def test_passes_through_the_verification_flag(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]
        write.return_value = {"written": True, "verified": False}

        result = weight_sync.sync_weight()

        assert result["written"][0]["verified"] is False


class TestWindow:
    def test_clamps_a_huge_window(self, mocks) -> None:
        fetch, _read, _write = mocks
        fetch.return_value = []

        result = weight_sync.sync_weight(days=1000)

        assert result["window_days"] == weight_sync._MAX_DAYS
        fetch.assert_called_once_with(weight_sync._MAX_DAYS)

    def test_clamps_a_zero_window(self, mocks) -> None:
        fetch, _read, _write = mocks
        fetch.return_value = []

        assert weight_sync.sync_weight(days=0)["window_days"] == 1

    def test_empty_result_points_at_zepp(self, mocks) -> None:
        fetch, _read, _write = mocks
        fetch.return_value = []

        result = weight_sync.sync_weight()

        assert "Zepp Life" in result["note"]
        assert result["xiaomi"]["weigh_ins"] == 0
