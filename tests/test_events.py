from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from garmin_mcp_lite.tools.events import get_events


def _event(name: str, day_offset: int | None) -> dict:
    date = None if day_offset is None else (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
    return {
        "eventName": name, "date": date, "eventType": "running",
        "completionTarget": None, "eventCustomization": None,
    }


class TestGetEvents:
    def test_returns_events(self) -> None:
        result = get_events()
        assert result["count"] == 2
        marathon = result["events"][1]
        assert marathon["name"] == "Tokyo Marathon"
        assert marathon["distance_km"] == 42.195
        assert marathon["goal_time"] == "4:00:00"
        assert marathon["is_primary"] is True
        assert marathon["training_plan_id"] == "plan_marathon"

    def test_past_events_are_dropped_and_upcoming_sorted_soonest_first(self) -> None:
        result = get_events()
        names = [event["name"] for event in result["events"]]
        assert names == ["Local 10K", "Tokyo Marathon"]

    def test_event_without_a_goal_is_still_listed(self) -> None:
        # Garmin sends `customGoal: null` and `completionTarget: null` here;
        # `.get(key, {})` does not cover that and used to raise AttributeError.
        result = get_events()
        event = result["events"][0]
        assert event["name"] == "Local 10K"
        assert event["distance_km"] is None
        assert event["goal_time"] is None
        assert event["is_primary"] is False

    def test_event_with_unparseable_date_is_kept_last(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = None
        mock_get_client.connectapi.return_value = [
            _event("Undated", None),
            _event("Far Future", 400),
        ]
        result = get_events()
        assert [event["name"] for event in result["events"]] == ["Far Future", "Undated"]

    def test_today_event_is_included(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = None
        mock_get_client.connectapi.return_value = [_event("Race Day", 0)]
        result = get_events()
        assert result["count"] == 1

    def test_endpoint_failure_returns_error_dict(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = RuntimeError("calendar down")
        assert get_events() == {"error": "calendar down"}

    def test_null_response_is_treated_as_no_events(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = None
        mock_get_client.connectapi.return_value = None
        assert get_events() == {"count": 0, "events": []}
