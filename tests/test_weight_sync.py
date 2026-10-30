"""Tests for the Xiaomi -> Garmin weight sync.

The behaviour that matters is what it refuses to do: write a day Garmin already
has, write twice for one day, or write anything at all when the Xiaomi token is
missing. Those are the cases a user cannot easily undo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from garmin_mcp_lite.tools import weight_sync
from garmin_mcp_lite.xiaomi import XiaomiError


def _record(day: str, weight: float = 71.2, **extra) -> dict:
    return {"date": day, "timestamp": f"{day}T07:00:00", "weight_kg": weight, "source": "yunmai", **extra}


def _wall(day: str, time: str = "07:00:00") -> float:
    """A wall-clock moment as the seconds Garmin's `date` field reduces to."""
    return datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=UTC).timestamp()


def _garmin(*rows: tuple[str, str]) -> dict:
    """A get_weigh_ins payload; each row is (day, time)."""
    by_day: dict[str, list[dict]] = {}
    for day, time in rows:
        by_day.setdefault(day, []).append(
            {"calendarDate": day, "date": int(_wall(day, time) * 1000), "weight": 71000.0, "sourceType": "INDEX_SCALE"}
        )
    return {"dailyWeightSummaries": [{"summaryDate": day, "allWeightMetrics": items} for day, items in by_day.items()]}


@pytest.fixture()
def mocks():
    with (
        patch.object(weight_sync, "fetch_weights") as fetch,
        patch.object(weight_sync, "get_body_composition") as read,
        patch.object(weight_sync, "_write_composition") as write,
        patch.object(weight_sync, "get_client") as client,
        patch.object(weight_sync, "_account_offset") as offset,
    ):
        read.return_value = {"count": 0, "records": []}
        write.return_value = {"written": True, "verified": True}
        # No zone proven by the window: the timestamps go out unchanged, which is
        # the behaviour every test not about timezones should be exercising.
        offset.return_value = None
        client.return_value.get_weigh_ins.return_value = {"dailyWeightSummaries": []}
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
    def test_skips_a_weighing_garmin_already_has(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20", 71.0), _record("2026-10-21", 71.2)]

        with patch.object(weight_sync, "_window_clocks", return_value={"2026-10-20": [_wall("2026-10-20")]}):
            result = weight_sync.sync_weight()

        assert [item["date"] for item in result["written"]] == ["2026-10-21"]
        assert [item["date"] for item in result["skipped"]] == ["2026-10-20"]
        assert result["garmin"]["weigh_ins_already_present"] == 1
        write.assert_called_once()

    def test_is_idempotent(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]

        with patch.object(weight_sync, "_window_clocks", return_value={"2026-10-20": [_wall("2026-10-20")]}):
            result = weight_sync.sync_weight()

        assert result["written"] == []
        assert len(result["skipped"]) == 1
        write.assert_not_called()

    def test_every_weighing_of_a_day_gets_its_own_entry(self, mocks) -> None:
        # Morning fasted and evening before bed are two measurements, not one
        # reported twice — the whole point of matching by moment rather than by day.
        fetch, _read, write = mocks
        fetch.return_value = [
            {"date": "2026-10-20", "timestamp": "2026-10-20T21:30:00", "weight_kg": 72.4, "source": "x"},
            {"date": "2026-10-20", "timestamp": "2026-10-20T06:45:00", "weight_kg": 71.2, "source": "x"},
            {"date": "2026-10-20", "timestamp": "2026-10-20T12:00:00", "weight_kg": 71.8, "source": "x"},
        ]

        result = weight_sync.sync_weight()

        assert write.call_count == 3
        assert [item["time"][-8:] for item in result["written"]] == ["06:45:00", "12:00:00", "21:30:00"]
        assert result["xiaomi"]["duplicates_merged"] == 0

    def test_a_second_weighing_lands_beside_the_first(self, mocks) -> None:
        # The morning is already on Garmin; the evening one is not, and skipping
        # the whole day — what this used to do — would lose it.
        fetch, _read, write = mocks
        fetch.return_value = [
            _record("2026-10-20", 71.2, timestamp="2026-10-20T07:00:00"),
            _record("2026-10-20", 72.4, timestamp="2026-10-20T21:30:00"),
        ]

        with patch.object(
            weight_sync, "_window_clocks", return_value={"2026-10-20": [_wall("2026-10-20", "07:00:00")]}
        ):
            result = weight_sync.sync_weight()

        assert [item["time"] for item in result["written"]] == ["2026-10-20T21:30:00"]
        assert [item["time"] for item in result["skipped"]] == ["2026-10-20T07:00:00"]
        write.assert_called_once()

    def test_the_scales_double_upload_is_folded_into_the_richer_row(self, mocks) -> None:
        # A weight-only row, then the full body-composition row seconds later: one
        # measurement reported twice. Writing both would put two entries on Garmin
        # for one step onto the scale.
        fetch, _read, write = mocks
        fetch.return_value = [
            {"date": "2026-10-20", "timestamp": "2026-10-20T07:00:00", "weight_kg": 71.2, "source": "x"},
            {
                "date": "2026-10-20",
                "timestamp": "2026-10-20T07:00:04",
                "weight_kg": 71.2,
                "source": "x",
                "body_fat_pct": 16.5,
                "body_water_pct": 55.1,
                "bmi": 22.1,
            },
        ]

        result = weight_sync.sync_weight()

        assert write.call_count == 1
        assert write.call_args.kwargs["body_fat"] == 16.5
        assert result["xiaomi"]["duplicates_merged"] == 1

    def test_an_untimed_garmin_row_counts_as_the_whole_day(self, mocks) -> None:
        # Without a time there is no way to tell one weighing from another, and
        # writing blind would put a duplicate on top of it.
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]

        with patch.object(weight_sync, "_window_clocks", return_value={"2026-10-20": [None]}):
            result = weight_sync.sync_weight()

        assert result["written"] == []
        write.assert_not_called()

    def test_an_old_garminconnect_falls_back_to_the_day_summary(self, mocks) -> None:
        # get_weigh_ins() is missing on the oldest supported releases; the day
        # summary still says which days are taken, just not at what time.
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20")]
        read.return_value = {"records": [{"date": "2026-10-20", "weight_kg": 71.0}]}

        with patch.object(weight_sync, "_window_clocks", side_effect=AttributeError("no get_weigh_ins")):
            result = weight_sync.sync_weight()

        assert result["written"] == []
        write.assert_not_called()


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
        assert kwargs["value"] == 71.2
        assert kwargs["timestamp"] == "2026-10-20T07:00:00"
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


class TestPlausibility:
    """Garmin keeps every entry forever, so a bad weight must never be written."""

    def _garmin_history(self) -> dict:
        return {
            "records": [
                {"date": "2026-10-17", "weight_kg": 71.0},
                {"date": "2026-10-18", "weight_kg": 71.2},
                {"date": "2026-10-19", "weight_kg": 71.4},
            ]
        }

    def test_refuses_a_weight_that_doubles_the_garmin_median(self, mocks) -> None:
        # 斤 reads exactly 2× kg: a 71 kg person would arrive as ~142.
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20", 142.4)]
        read.return_value = self._garmin_history()

        result = weight_sync.sync_weight()

        assert result["written"] == []
        assert result["skipped"][0]["date"] == "2026-10-20"
        assert "unit mix-up" in result["skipped"][0]["reason"]
        assert result["garmin"]["plausibility_baseline_kg"] == 71.2
        write.assert_not_called()

    def test_accepts_normal_fluctuation_around_the_median(self, mocks) -> None:
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20", 75.0)]
        read.return_value = self._garmin_history()

        result = weight_sync.sync_weight()

        assert [item["date"] for item in result["written"]] == ["2026-10-20"]
        write.assert_called_once()

    def test_without_history_absolute_bounds_apply(self, mocks) -> None:
        # Two Garmin points are not enough for a median, so the wide bounds rule.
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20", 300.0)]
        read.return_value = {"records": [{"date": "2026-10-19", "weight_kg": 71.0}]}

        result = weight_sync.sync_weight()

        assert result["written"] == []
        assert "outside 30–250 kg" in result["skipped"][0]["reason"]
        assert result["garmin"]["plausibility_baseline_kg"] is None
        write.assert_not_called()

    def test_median_of_an_even_history_is_the_midpoint(self, mocks) -> None:
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20", 142.4)]
        read.return_value = {
            "records": [
                {"date": "2026-10-16", "weight_kg": 70.0},
                {"date": "2026-10-17", "weight_kg": 71.0},
                {"date": "2026-10-18", "weight_kg": 72.0},
                {"date": "2026-10-19", "weight_kg": 73.0},
            ]
        }

        result = weight_sync.sync_weight()

        assert result["garmin"]["plausibility_baseline_kg"] == 71.5
        assert result["written"] == []
        write.assert_not_called()

    def test_dry_run_reports_the_refusal_without_writing(self, mocks) -> None:
        fetch, read, write = mocks
        fetch.return_value = [_record("2026-10-20", 142.4)]
        read.return_value = self._garmin_history()

        result = weight_sync.sync_weight(dry_run=True)

        assert result["written"] == []
        assert "unit mix-up" in result["skipped"][0]["reason"]
        write.assert_not_called()


class TestPacing:
    def test_pauses_between_writes_but_not_before_the_first(self, mocks) -> None:
        fetch, _read, _write = mocks
        fetch.return_value = [_record("2026-10-18"), _record("2026-10-19"), _record("2026-10-20")]

        with patch.object(weight_sync.time, "sleep") as sleep:
            weight_sync.sync_weight()

        assert sleep.call_count == 2  # between writes only, never before the first
        sleep.assert_called_with(weight_sync._WRITE_PAUSE_S)


class TestVerificationWarning:
    def test_unverified_writes_raise_a_timezone_warning(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]
        write.return_value = {"written": True, "verified": False}

        result = weight_sync.sync_weight()

        assert "timezone" in result["warning"]

    def test_verified_writes_stay_quiet(self, mocks) -> None:
        fetch, _read, _write = mocks
        fetch.return_value = [_record("2026-10-20")]

        result = weight_sync.sync_weight()

        assert "warning" not in result


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


class TestGarminFailure:
    """What happens when the Garmin side is the thing that is broken."""

    def test_a_missing_garmin_token_is_reported_not_raised(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]

        with patch.object(weight_sync, "get_client", side_effect=RuntimeError("Garmin token not found")):
            result = weight_sync.sync_weight()

        assert "Garmin token not found" in result["error"]
        assert result["written"] == []
        write.assert_not_called()

    def test_an_unreadable_zone_does_not_stop_the_sync(self, mocks) -> None:
        # Without a zone the timestamps go out unchanged, which is what every
        # version before this did. Failing the whole run over it would be worse.
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]

        with patch.object(weight_sync, "_account_offset", side_effect=RuntimeError("read down")):
            result = weight_sync.sync_weight()

        assert len(result["written"]) == 1
        assert write.call_args.kwargs["account_offset_s"] is None
        assert result["garmin"]["account_offset_hours"] is None

    def test_the_window_zone_is_passed_to_the_write(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20")]

        with patch.object(weight_sync, "_account_offset", return_value=8 * 3600):
            result = weight_sync.sync_weight()

        assert write.call_args.kwargs["account_offset_s"] == 8 * 3600
        assert result["garmin"]["account_offset_hours"] == 8.0


class TestRateLimits:
    """What a backfill does when Garmin starts refusing writes for going too fast.

    Both halves matter. Hammering on only lengthens the block, and stopping has to
    be safe — which it is exactly because a day already written is skipped on the
    next run.
    """

    def test_a_rate_limited_write_stops_the_run(self, mocks) -> None:
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20"), _record("2026-10-21")]
        write.side_effect = [{"error": "Rate limit exceeded", "written": False, "rate_limited": True}]

        result = weight_sync.sync_weight()

        assert write.call_count == 1  # the second day is never attempted
        assert result["written"] == []
        assert result["failed"][0]["date"] == "2026-10-20"
        assert "rate-limited the run after 0 writes" in result["stopped_early"]

    def test_a_plain_failure_does_not_stop_the_run(self, mocks) -> None:
        # One rejected day is Garmin's opinion of that day; only a rate limit says
        # something about every day still to come.
        fetch, _read, write = mocks
        fetch.return_value = [_record("2026-10-20"), _record("2026-10-21")]
        write.side_effect = [{"error": "upload refused", "written": False}, {"written": True, "verified": True}]

        with patch.object(weight_sync.time, "sleep"):
            result = weight_sync.sync_weight()

        assert write.call_count == 2
        assert [item["date"] for item in result["written"]] == ["2026-10-21"]
        assert "stopped_early" not in result


class TestReadingGarminsRows:
    """The two fields Garmin returns per weighing are not the same time."""

    def test_the_wall_clock_is_preferred_over_the_instant(self) -> None:
        # `date` is the clock in the account's zone; `timestampGMT` the true
        # instant, eight hours earlier on a China account. Only the first is
        # comparable to a Xiaomi timestamp, which carries no zone at all.
        row = {"date": 1792654799000, "timestampGMT": 1792625999000}

        assert weight_sync._row_clock(row) == _wall("2026-10-22", "07:39:59")

    def test_without_a_wall_clock_the_instant_is_the_fallback(self) -> None:
        row = {"timestampGMT": 1792680357000}

        # Read through the machine's zone, which is the best guess available when
        # Garmin gives nothing better.
        assert weight_sync._row_clock(row) == datetime.fromtimestamp(1792680357).replace(tzinfo=UTC).timestamp()

    def test_a_row_with_neither_time_has_no_clock(self) -> None:
        assert weight_sync._row_clock({}) is None

    def test_the_window_reads_every_weighing_not_just_one_a_day(self, mock_get_client) -> None:
        # get_body_composition collapses a day to one row; this is the only view
        # that shows both the morning and the evening weighing.
        mock_get_client.get_weigh_ins.return_value = {
            "dailyWeightSummaries": [
                {
                    "summaryDate": "2026-10-22",
                    "allWeightMetrics": [
                        {"calendarDate": "2026-10-22", "date": int(_wall("2026-10-22", "07:39:59") * 1000)},
                        {"calendarDate": "2026-10-22", "date": int(_wall("2026-10-22", "22:45:57") * 1000)},
                    ],
                },
                "not a summary",
                {"allWeightMetrics": [{"date": 1792709157000}]},  # no calendarDate
            ]
        }

        clocks = weight_sync._window_clocks(mock_get_client, "2026-10-22", "2026-10-22")

        assert sorted(clocks) == ["2026-10-22"]
        assert len(clocks["2026-10-22"]) == 2
