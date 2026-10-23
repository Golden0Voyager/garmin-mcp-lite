"""Tests for _common.py utilities (pure functions, no mocking needed)."""

from __future__ import annotations

from garmin_mcp_lite.tools._common import (
    activity_local_date,
    activity_type_key,
    as_dict,
    as_list,
    days_ago_str,
    format_duration,
    format_pace,
    get_first,
    pace_from_speed,
    summarize_activity,
    today_str,
)


class TestAsDict:
    def test_passes_a_dict_through(self) -> None:
        assert as_dict({"a": 1}) == {"a": 1}

    def test_turns_none_into_an_empty_dict(self) -> None:
        # This is the case `payload.get("key", {})` gets wrong: Garmin sends an
        # explicit null, so the default never applies.
        assert as_dict(None) == {}

    def test_turns_other_types_into_an_empty_dict(self) -> None:
        assert as_dict([1, 2]) == {}
        assert as_dict("text") == {}


class TestAsList:
    def test_passes_a_list_through(self) -> None:
        assert as_list([1, 2]) == [1, 2]

    def test_turns_none_into_an_empty_list(self) -> None:
        assert as_list(None) == []

    def test_turns_other_types_into_an_empty_list(self) -> None:
        assert as_list({"a": 1}) == []



class TestTodayStr:
    def test_returns_iso_format(self) -> None:
        val = today_str()
        parts = val.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2
        assert len(parts[2]) == 2


class TestDaysAgoStr:
    def test_returns_past_date(self) -> None:
        val = days_ago_str(7)
        parts = val.split("-")
        assert len(parts) == 3


class TestGetFirst:
    def test_finds_existing_key(self) -> None:
        d = {"a": 1, "b": 2}
        assert get_first(d, "b", "a") == 2

    def test_returns_none_for_empty_dict(self) -> None:
        assert get_first({}, "a") is None

    def test_returns_none_for_none(self) -> None:
        assert get_first(None, "a") is None


class TestPaceFromSpeed:
    def test_returns_none_for_zero(self) -> None:
        assert pace_from_speed(0) is None

    def test_returns_none_for_none(self) -> None:
        assert pace_from_speed(None) is None

    def test_computes_pace_correctly(self) -> None:
        # 2.81 m/s ≈ 5:56 /km
        result = pace_from_speed(2.81)
        assert result == "05:55"

    def test_handles_fast_speed(self) -> None:
        # 5.0 m/s ≈ 3:20 /km
        result = pace_from_speed(5.0)
        assert result == "03:20"


class TestFormatDuration:
    def test_under_an_hour(self) -> None:
        assert format_duration(1295) == "21:35"

    def test_over_an_hour(self) -> None:
        assert format_duration(6249) == "1:44:09"

    def test_rounds_seconds(self) -> None:
        assert format_duration(219.94) == "3:40"

    def test_returns_none_for_none(self) -> None:
        assert format_duration(None) is None


class TestFormatPace:
    def test_pads_to_mm_ss(self) -> None:
        assert format_pace(259) == "04:19"

    def test_handles_pace_over_ten_minutes(self) -> None:
        assert format_pace(605) == "10:05"

    def test_returns_none_for_zero(self) -> None:
        assert format_pace(0) is None

    def test_returns_none_for_none(self) -> None:
        assert format_pace(None) is None


class TestActivityTypeKey:
    def test_extracts_type_key(self) -> None:
        activity = {"activityType": {"typeKey": "running"}}
        assert activity_type_key(activity) == "running"

    def test_lowercases(self) -> None:
        activity = {"activityType": {"typeKey": "CyCliNg"}}
        assert activity_type_key(activity) == "cycling"

    def test_returns_empty_for_missing(self) -> None:
        assert activity_type_key({}) == ""


class TestActivityLocalDate:
    def test_extracts_date_from_iso(self) -> None:
        activity = {"startTimeLocal": "2026-06-18 07:30:00"}
        assert activity_local_date(activity) == "2026-06-18"

    def test_returns_none_for_missing(self) -> None:
        assert activity_local_date({}) is None


class TestSummarizeActivity:
    def test_summarizes_running_activity(self) -> None:
        activity = {
            "activityId": 123,
            "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "startTimeLocal": "2026-06-18T07:30:00",
            "distance": 5230.0,
            "duration": 1860.0,
            "calories": 420,
            "averageHR": 148,
            "maxHR": 172,
            "averageSpeed": 2.81,
        }
        result = summarize_activity(activity)
        assert result["id"] == 123
        assert result["name"] == "Morning Run"
        assert result["type"] == "running"
        assert result["distance_km"] == 5.23
        assert result["duration_min"] == 31
        assert result["calories"] == 420
        assert result["avg_hr"] == 148
        assert result["max_hr"] == 172
        assert result["pace"] == "05:55"

    def test_handles_missing_fields(self) -> None:
        result = summarize_activity({})
        assert result["distance_km"] is None
        assert result["duration_min"] is None
        assert result["calories"] is None
