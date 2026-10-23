from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.events import get_events


class TestGetEvents:
    def test_returns_events(self) -> None:
        result = get_events()
        assert result["count"] == 2
        event = result["events"][0]
        assert event["name"] == "Tokyo Marathon"
        assert event["distance_km"] == 42.195
        assert event["goal_time"] == "4:00:00"
        assert event["is_primary"] is True
        assert event["training_plan_id"] == "plan_marathon"

    def test_event_without_a_goal_is_still_listed(self) -> None:
        # Garmin sends `customGoal: null` and `completionTarget: null` here;
        # `.get(key, {})` does not cover that and used to raise AttributeError.
        result = get_events()
        event = result["events"][1]
        assert event["name"] == "Local 10K"
        assert event["distance_km"] is None
        assert event["goal_time"] is None
        assert event["is_primary"] is False

    def test_endpoint_failure_returns_error_dict(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = RuntimeError("calendar down")
        assert get_events() == {"error": "calendar down"}

    def test_null_response_is_treated_as_no_events(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = None
        mock_get_client.connectapi.return_value = None
        assert get_events() == {"count": 0, "events": []}
