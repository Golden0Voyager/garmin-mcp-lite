"""Tests for _common.py utilities (pure functions, no mocking needed)."""

from __future__ import annotations

from garmin_mcp_lite.tools._common import (
    activity_local_date,
    activity_type_key,
    days_ago_str,
    get_first,
    pace_from_speed,
    summarize_activity,
    today_str,
)


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
