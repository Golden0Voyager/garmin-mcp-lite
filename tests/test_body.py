from __future__ import annotations

import contextlib
import os
import re
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from garminconnect.exceptions import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)
from requests import HTTPError

from garmin_mcp_lite.tools import body as body_mod
from garmin_mcp_lite.tools._common import today_str
from garmin_mcp_lite.tools.body import add_body_composition, get_body_composition

_ISO_SECONDS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class TestMassNormalisation:
    def test_grams_become_kilograms(self, mock_get_client: MagicMock) -> None:
        record = get_body_composition()["records"][0]

        assert record["weight_kg"] == 69.8
        assert record["muscle_mass_kg"] == 32.1
        assert record["bone_mass_kg"] == 3.1

    def test_values_already_in_kilograms_are_left_alone(self, mock_get_client: MagicMock) -> None:
        # A third-party scale can push kilograms upstream; 70.2 must not become 0.07.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"calendarDate": "2026-01-01", "weight": 70.2, "muscleMass": 32.1}],
        }

        record = get_body_composition()["records"][0]

        assert record["weight_kg"] == 70.2
        assert record["muscle_mass_kg"] == 32.1

    def test_zero_and_negative_mass_are_treated_as_missing(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"calendarDate": "2026-01-01", "weight": 0, "muscleMass": -5}],
        }

        record = get_body_composition()["records"][0]

        assert record == {"date": "2026-01-01"}

    def test_booleans_are_not_numbers(self, mock_get_client: MagicMock) -> None:
        # isinstance(True, int) is True in Python; a naive check would emit 1 kg.
        assert body_mod._to_kg(True) is None
        assert body_mod._to_kg(None) is None
        assert body_mod._to_kg("69.8") is None


class TestGetBodyComposition:
    def test_records_are_newest_first(self, mock_get_client: MagicMock) -> None:
        dates = [r["date"] for r in get_body_composition()["records"]]

        assert dates == ["2025-09-26", "2025-09-20"]

    def test_null_fields_are_dropped(self, mock_get_client: MagicMock) -> None:
        # An MFP-synced row only has weight. Emitting eight nulls wastes tokens and
        # makes the model report "body fat: null" as if it were a measurement.
        oldest = get_body_composition()["records"][1]

        assert oldest == {"date": "2025-09-20", "weight_kg": 70.2, "source": "MFP"}

    def test_full_metrics_are_returned(self, mock_get_client: MagicMock) -> None:
        latest = get_body_composition()["latest"]

        assert latest["bmi"] == 22.1
        assert latest["body_fat_pct"] == 18.4
        assert latest["body_water_pct"] == 55.2
        assert latest["visceral_fat"] == 8
        assert latest["metabolic_age"] == 36
        assert latest["source"] == "INDEX_SCALE"

    def test_change_is_newest_minus_oldest(self, mock_get_client: MagicMock) -> None:
        change = get_body_composition()["change"]

        assert change == {"weight_kg": -0.4, "from": "2025-09-20", "to": "2025-09-26"}

    def test_average_comes_from_total_average(self, mock_get_client: MagicMock) -> None:
        assert get_body_composition()["average"] == {"weight_kg": 70.0}

    def test_average_carries_body_fat_when_garmin_computes_it(self, mock_get_client: MagicMock) -> None:
        # totalAverage has the same shape as a row, so a populated account gets
        # averages for the composition metrics too.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"calendarDate": "2026-01-01", "weight": 70000.0}],
            "totalAverage": {"weight": 70000.0, "bmi": 22.14, "bodyFat": 18.44, "bodyWater": 55.25},
        }

        average = get_body_composition()["average"]

        assert average == {"weight_kg": 70.0, "bmi": 22.14, "body_fat_pct": 18.44, "body_water_pct": 55.25}

    def test_count_reports_every_row_not_the_limited_page(self, mock_get_client: MagicMock) -> None:
        result = get_body_composition(limit=1)

        assert result["count"] == 2
        assert len(result["records"]) == 1

    def test_empty_history(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {"dateWeightList": []}

        result = get_body_composition()

        assert result["count"] == 0
        assert result["records"] == []
        assert result["latest"] is None
        assert "change" not in result

    def test_null_payload_does_not_raise(self, mock_get_client: MagicMock) -> None:
        # Garmin answers an empty window with explicit nulls, not an empty list.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = None

        assert get_body_composition()["records"] == []

    def test_api_failure_returns_error(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = RuntimeError("boom")

        assert get_body_composition()["error"] == "boom"

    def test_days_are_clamped(self, mock_get_client: MagicMock) -> None:
        get_body_composition(days=99999)

        start, end = mock_get_client.get_body_composition.call_args[0]
        expected = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
        assert start == expected
        assert end == today_str()


class TestAddBodyComposition:
    def test_writes_the_measurement(self, mock_get_client: MagicMock) -> None:
        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["written"] is True
        assert result["weight_kg"] == 70.5
        assert result["date"] == "2026-10-23"

    def test_forwards_every_metric_under_the_library_keyword_names(
        self, mock_get_client: MagicMock
    ) -> None:
        add_body_composition(
            weight=70.5,
            date="2026-10-23",
            body_fat=18.4,
            body_water=55.2,
            muscle_mass=32.1,
            bone_mass=3.1,
            bmi=22.1,
            basal_met=1650,
            metabolic_age=36,
        )

        kwargs = mock_get_client.add_body_composition.call_args.kwargs
        # The public API uses percent_fat / percent_hydration, not body_fat /
        # body_water; a silent rename here would drop the metric on the floor.
        # Every number is padded by a millionth (see _fit_scaled), so compare
        # numerically rather than exactly.
        assert kwargs["weight"] == pytest.approx(70.5)
        assert kwargs["percent_fat"] == pytest.approx(18.4)
        assert kwargs["percent_hydration"] == pytest.approx(55.2)
        assert kwargs["muscle_mass"] == pytest.approx(32.1)
        assert kwargs["bone_mass"] == pytest.approx(3.1)
        assert kwargs["bmi"] == pytest.approx(22.1)
        assert kwargs["basal_met"] == 1650
        assert kwargs["metabolic_age"] == 36

    def test_bare_date_is_recorded_in_the_morning(self, mock_get_client: MagicMock) -> None:
        add_body_composition(weight=70.5, date="2026-10-23")

        assert mock_get_client.add_body_composition.call_args.kwargs["timestamp"] == "2026-10-23T07:00:00"

    def test_full_timestamp_is_preserved(self, mock_get_client: MagicMock) -> None:
        add_body_composition(weight=70.5, date="2026-10-23T21:15:30")

        assert mock_get_client.add_body_composition.call_args.kwargs["timestamp"] == "2026-10-23T21:15:30"

    def test_missing_date_defaults_to_now(self, mock_get_client: MagicMock) -> None:
        add_body_composition(weight=70.5)

        timestamp = mock_get_client.add_body_composition.call_args.kwargs["timestamp"]
        assert _ISO_SECONDS.match(timestamp)

    def test_invalid_date_is_rejected(self, mock_get_client: MagicMock) -> None:
        with pytest.raises(ValueError, match="ISO 8601"):
            add_body_composition(weight=70.5, date="23/10/2026")

    def test_grams_are_rejected_with_a_pointer_to_the_cause(self, mock_get_client: MagicMock) -> None:
        # The read path hands back grams, so a read-modify-write is the natural
        # way to get here. The message has to name the mistake.
        with pytest.raises(ValueError, match="looks like grams"):
            add_body_composition(weight=69800)

        mock_get_client.add_body_composition.assert_not_called()

    def test_non_positive_weight_is_rejected(self, mock_get_client: MagicMock) -> None:
        for bad in (0, -1):
            with pytest.raises(ValueError, match="positive"):
                add_body_composition(weight=bad)

    def test_non_numeric_weight_is_rejected(self, mock_get_client: MagicMock) -> None:
        with pytest.raises(ValueError, match="must be a number"):
            add_body_composition(weight="70.5")  # type: ignore[arg-type]

    def test_boolean_weight_is_rejected(self, mock_get_client: MagicMock) -> None:
        with pytest.raises(ValueError, match="must be a number"):
            add_body_composition(weight=True)

    def test_only_supplied_metrics_are_echoed(self, mock_get_client: MagicMock) -> None:
        result = add_body_composition(weight=70.5, body_fat=18.4)

        assert result["body_fat_pct"] == 18.4
        assert "bmi" not in result
        assert "muscle_mass_kg" not in result

    def test_upload_status_is_reported(self, mock_get_client: MagicMock) -> None:
        assert add_body_composition(weight=70.5)["garmin_status"] == "SUCCESS"

    def test_missing_status_is_tolerated(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.return_value = None

        result = add_body_composition(weight=70.5)

        assert result["written"] is True
        assert "garmin_status" not in result

    def test_absent_status_falls_back_to_reading_the_day_back(self, mock_get_client: MagicMock) -> None:
        # Live testing showed the upload response can carry no status at all, so
        # the tool has to confirm the entry by reading it back.
        mock_get_client.add_body_composition.return_value = {}
        mock_get_client.get_body_composition.side_effect = [
            {"dateWeightList": []},  # pre-write duplicate check
            {"dateWeightList": [{"calendarDate": "2026-10-23", "weight": 70500.0, "sourceType": "INDEX_SCALE"}]},
        ]

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["verified"] is True
        assert result["stored"] == {"weight_kg": 70.5, "source": "INDEX_SCALE"}

    def test_readback_that_disagrees_is_not_verified(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.return_value = {}
        mock_get_client.get_body_composition.side_effect = [
            {"dateWeightList": []},
            {"dateWeightList": [{"calendarDate": "2026-10-23", "weight": 75000.0}]},
        ]

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["verified"] is False

    def test_readback_that_finds_nothing_is_not_verified(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.return_value = {}
        mock_get_client.get_body_composition.side_effect = [
            {"dateWeightList": []},
            {"dateWeightList": []},
        ]

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["verified"] is False
        assert "stored" not in result

    def test_duplicate_day_produces_a_warning(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"calendarDate": "2026-10-23", "weight": 70200.0, "sourceType": "MFP"}],
        }

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert "already had 70.2 kg" in result["warning"]
        assert "MFP" in result["warning"]
        # The write still happens: Garmin is the one that decides about duplicates.
        assert result["written"] is True

    def test_fresh_day_has_no_warning(self, mock_get_client: MagicMock) -> None:
        assert "warning" not in add_body_composition(weight=70.5, date="2026-10-23")

    def test_lookup_failure_does_not_block_the_write(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = RuntimeError("lookup down")

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["written"] is True

    def test_api_failure_returns_error(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.side_effect = RuntimeError("upload rejected")

        result = add_body_composition(weight=70.5)

        assert result["written"] is False
        assert result["error"] == "upload rejected"

    def test_old_garminconnect_gets_a_readable_error(self) -> None:
        # add_body_composition() is missing from the oldest versions this package
        # still allows; an AttributeError would tell the user nothing.
        legacy = MagicMock(spec=["get_body_composition"])

        with patch.object(body_mod, "get_client", return_value=legacy):
            result = add_body_composition(weight=70.5)

        assert result["written"] is False
        assert "garminconnect>=0.3.0" in result["error"]


@contextlib.contextmanager
def _machine_in(zone: str):
    """Run the block as if this machine sat in `zone`."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = zone
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def _http_429(headers: dict | None = None) -> HTTPError:
    """The HTTP error garminconnect wraps a rate limit in."""
    return HTTPError("429 Client Error: Too Many Requests", response=MagicMock(status_code=429, headers=headers or {}))


def _too_many_requests(headers: dict | None = None) -> Exception:
    """What garminconnect 0.3 raises for a 429 — the domain error over the HTTP one."""
    exc = GarminConnectTooManyRequestsError("Rate limit exceeded")
    exc.__cause__ = _http_429(headers)
    return exc


class TestZoneCalibration:
    """Where a weighing lands has to survive the sync running from another timezone.

    Garmin stores two times per row: `date` is the wall clock in the account's
    zone, `timestampGMT` the true instant. Their difference *is* the zone, so it
    can be read off the rows already there instead of configured. Measured on the
    live account: the same 07:30 sent from a laptop in New York came back as
    19:30, twelve hours off, after which it no longer matched the scale and was
    written a second time.
    """

    def test_the_zone_is_the_difference_between_a_rows_two_timestamps(self) -> None:
        # The pair Garmin actually returned for one weighing on 2026-10-22.
        row = {"date": 1792709157000, "timestampGMT": 1792680357000}

        assert body_mod._row_offset(row) == 8 * 3600

    def test_a_row_with_half_the_pair_proves_nothing(self) -> None:
        assert body_mod._row_offset({"date": 1792709157000}) is None
        assert body_mod._row_offset({"timestampGMT": 1792680357000}) is None
        # A bool is an int in Python, and 0 is not a timestamp.
        assert body_mod._row_offset({"date": True, "timestampGMT": 1792680357000}) is None
        assert body_mod._row_offset({"date": 0, "timestampGMT": 1792680357000}) is None

    def test_the_days_rows_calibrate_the_entry_and_the_zone_together(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [
                "not a row",
                {"weight": 70200.0, "sourceType": "MFP", "date": 1792709157000, "timestampGMT": 1792680357000},
                {"weight": 70500.0, "sourceType": "INDEX_SCALE", "date": 1792709157000, "timestampGMT": 1792680357000},
            ]
        }

        state = body_mod._day_state(mock_get_client, "2026-10-22")

        assert state["existing"] == {"weight_kg": 70.2, "source": "MFP"}
        assert state["offset_s"] == 8 * 3600

    def test_a_day_that_cannot_be_read_says_nothing(self, mock_get_client: MagicMock) -> None:
        # The caller falls back to sending the timestamp unchanged, which is what
        # every version before this did — a failed probe must not fail the write.
        mock_get_client.get_body_composition.side_effect = RuntimeError("read down")

        assert body_mod._day_state(mock_get_client, "2026-10-22") == {}

    def test_a_row_without_a_pair_contributes_no_zone(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"weight": 70200.0, "sourceType": "MFP"}]
        }

        state = body_mod._day_state(mock_get_client, "2026-10-22")

        assert state["existing"] == {"weight_kg": 70.2, "source": "MFP"}
        assert "offset_s" not in state

    def test_the_window_zone_is_the_median_not_one_stray_row(self, mock_get_client: MagicMock) -> None:
        # One row that arrived by another route must not decide where every
        # weighing lands, so the median is used rather than the first or last.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [
                {"date": 1792709157000, "timestampGMT": 1792680357000},  # +8h
                {"date": 1792709157000, "timestampGMT": 1792680357000},  # +8h
                {"date": 1792709157000, "timestampGMT": 1792709157000},  # 0 — the stray
            ]
        }

        assert body_mod._account_offset(mock_get_client, "2026-09-30", "2026-10-30") == 8 * 3600

    def test_a_window_with_no_usable_pair_returns_no_zone(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {"dateWeightList": []}

        assert body_mod._account_offset(mock_get_client, "2026-09-30", "2026-10-30") is None

    def test_a_window_that_cannot_be_read_returns_no_zone(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = RuntimeError("read down")

        assert body_mod._account_offset(mock_get_client, "2026-09-30", "2026-10-30") is None

    def test_the_sent_string_round_trips_to_the_wall_clock(self) -> None:
        # garminconnect reads the string as machine-local; Garmin renders the
        # resulting instant in the account's zone. Composing the two has to give
        # back the clock the scale showed.
        sent = body_mod._sendable("2026-11-01T08:00:00", 8 * 3600)
        instant = time.mktime(datetime.fromisoformat(sent).timetuple())

        assert datetime.fromtimestamp(instant, UTC) == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)

    def test_it_holds_on_a_machine_twelve_hours_from_the_account(self) -> None:
        # The test above is satisfied by doing nothing at all when the machine
        # happens to sit in the account's zone: the correct and the broken version
        # then produce the same string. The bug only exists somewhere else, so it
        # has to be asserted from somewhere else.
        with _machine_in("America/New_York"):
            sent = body_mod._sendable("2026-11-01T08:00:00", 8 * 3600)
            instant = time.mktime(datetime.fromisoformat(sent).timetuple())

        assert datetime.fromtimestamp(instant, UTC) == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)

    def test_with_no_zone_known_the_timestamp_is_sent_unchanged(self) -> None:
        # An empty account proves nothing, and guessing shifts every weighing.
        assert body_mod._sendable("2026-11-01T08:00:00", None) == "2026-11-01T08:00:00"
        assert body_mod._sendable("2026-11-01T08:00:00", 0.0) == "2026-11-01T08:00:00"

    def test_the_day_in_the_report_is_the_one_the_caller_meant(self, mock_get_client: MagicMock) -> None:
        # The translated instant is only for the FIT file: the echoed date, the
        # duplicate check and the read-back all stay on the real day.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [
                {"weight": 70200.0, "sourceType": "MFP", "date": 1792709157000, "timestampGMT": 1792680357000}
            ]
        }
        mock_get_client.add_body_composition.return_value = {}

        result = add_body_composition(weight=70.5, date="2026-10-22T07:30:00")

        assert result["date"] == "2026-10-22"
        assert result["timestamp"] == "2026-10-22T07:30:00"
        assert "already had 70.2 kg" in result["warning"]

    def test_a_calibrated_zone_overrides_the_days_own(self, mock_get_client: MagicMock) -> None:
        # The sync calibrates over a whole window, which is more evidence than one
        # day's rows; the day-level probe is only the fallback.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"weight": 70200.0, "date": 1792709157000, "timestampGMT": 1792709157000}]
        }

        with _machine_in("America/New_York"):
            body_mod._write_composition(
                mock_get_client, value=70.5, timestamp="2026-10-22T07:30:00", account_offset_s=8 * 3600
            )
            sent = mock_get_client.add_body_composition.call_args.kwargs["timestamp"]
            instant = time.mktime(datetime.fromisoformat(sent).timetuple())

        # Not "whatever _sendable returns": the day's own rows say +0, the window
        # says +8, and +8 has to be the one that reaches the FIT file.
        assert datetime.fromtimestamp(instant, UTC) == datetime(2026, 10, 21, 23, 30, tzinfo=UTC)


class TestRateLimiting:
    """Garmin answers 429 when writes arrive too fast. That one is worth a wait."""

    def test_a_rate_limited_write_is_retried(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.side_effect = [
            _too_many_requests(),
            {"detailedImportResult": {"uploads": [{"status": "SUCCESS"}]}},
        ]

        with patch.object(body_mod.time, "sleep") as sleep:
            result = add_body_composition(weight=70.5)

        assert result["written"] is True
        assert sleep.call_count == 1
        assert sleep.call_args.args[0] == 2.0  # first backoff, before the doubling

    def test_the_second_wait_doubles(self, mock_get_client: MagicMock) -> None:
        # The second failure answers with an HTTP-date instead of a number of
        # seconds: unparseable means "fall back to the backoff", not "wait zero".
        mock_get_client.add_body_composition.side_effect = [
            _too_many_requests(),
            _too_many_requests({"Retry-After": "soon"}),
            {"detailedImportResult": {"uploads": [{"status": "SUCCESS"}]}},
        ]

        with patch.object(body_mod.time, "sleep") as sleep:
            add_body_composition(weight=70.5)

        assert [call.args[0] for call in sleep.call_args_list] == [2.0, 4.0]

    def test_garmins_own_retry_after_is_obeyed_and_capped(self, mock_get_client: MagicMock) -> None:
        # A Retry-After of an hour would otherwise hang the tool call.
        mock_get_client.add_body_composition.side_effect = [
            _too_many_requests({"Retry-After": "7"}),
            _too_many_requests({"Retry-After": "3600"}),
            {"detailedImportResult": {"uploads": [{"status": "SUCCESS"}]}},
        ]

        with patch.object(body_mod.time, "sleep") as sleep:
            add_body_composition(weight=70.5)

        # Garmin's own number wins over the doubling, up to the cap.
        assert [call.args[0] for call in sleep.call_args_list] == [7.0, 30.0]

    def test_giving_up_is_reported_as_a_rate_limit(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.side_effect = _too_many_requests()

        with patch.object(body_mod.time, "sleep") as sleep:
            result = add_body_composition(weight=70.5)

        assert result["written"] is False
        assert result["rate_limited"] is True
        assert "Rate limit exceeded" in result["error"]
        assert sleep.call_count == 2  # three attempts, so two waits

    def test_a_raw_http_error_is_recognised_too(self, mock_get_client: MagicMock) -> None:
        # Older garminconnect releases let the HTTP error through unwrapped.
        mock_get_client.add_body_composition.side_effect = [
            _http_429(),
            {"detailedImportResult": {"uploads": [{"status": "SUCCESS"}]}},
        ]

        with patch.object(body_mod.time, "sleep"):
            result = add_body_composition(weight=70.5)

        assert result["written"] is True

    def test_a_failure_garmin_cannot_retry_is_not_waited_for(self, mock_get_client: MagicMock) -> None:
        # A 401 is "your token is dead", and waiting will not fix that.
        mock_get_client.add_body_composition.side_effect = GarminConnectAuthenticationError("Authentication failed")

        with patch.object(body_mod.time, "sleep") as sleep:
            result = add_body_composition(weight=70.5)

        sleep.assert_not_called()
        assert result["written"] is False
        assert "rate_limited" not in result


def test_a_rate_limit_without_a_retry_after_header_falls_back_to_the_backoff() -> None:
    # Headers present but without Retry-After: the doubling is the answer, not zero.
    exc = _too_many_requests({"X-RateLimit-Remaining": "0"})

    assert body_mod._retry_after(exc) is None


def test_a_failed_read_back_does_not_fail_the_write(mock_get_client: MagicMock) -> None:
    # No status in the upload response, so the day is read back — and that read is
    # allowed to fail without failing the write.
    mock_get_client.add_body_composition.return_value = {}
    mock_get_client.get_body_composition.side_effect = RuntimeError("read down")

    result = add_body_composition(weight=70.5, date="2026-10-22T07:30:00")

    assert result["written"] is True
    assert result["verified"] is False
