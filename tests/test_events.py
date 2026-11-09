from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from garmin_mcp_lite.tools.events import add_event, delete_event, get_events


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

    def test_meter_distance_normalized_to_km(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = None
        mock_get_client.connectapi.return_value = [
            {
                "eventName": "Jiaxing Half",
                "date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
                "eventType": "running",
                "completionTarget": {"value": 21098.0, "unit": "meter"},
                "eventCustomization": None,
            }
        ]
        result = get_events()
        assert result["events"][0]["distance_km"] == 21.1

    def test_mile_distance_normalized_to_km(self, mock_get_client: MagicMock) -> None:
        mock_get_client.connectapi.side_effect = None
        mock_get_client.connectapi.return_value = [
            {
                "eventName": "US 10 Miler",
                "date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
                "eventType": "running",
                "completionTarget": {"value": 10.0, "unit": "mile"},
                "eventCustomization": None,
            }
        ]
        result = get_events()
        assert result["events"][0]["distance_km"] == 16.09


class TestAddEvent:
    def test_add_event_success(self, mock_get_client: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 88888, "eventName": "Jiaxing Marathon", "date": "2026-11-22"}
        mock_get_client.client._run_request.return_value = mock_resp

        res = add_event(
            name="Jiaxing Marathon",
            date="2026-11-22",
            distance_km=21.0975,
            goal_time="1:32:05",
            is_primary=True,
            start_time="07:30",
            location="Jiaxing",
        )

        assert res["ok"] is True
        assert res["event_id"] == 88888
        assert res["name"] == "Jiaxing Marathon"
        assert res["date"] == "2026-11-22"

        mock_get_client.client._run_request.assert_called_once()
        call_args = mock_get_client.client._run_request.call_args
        assert call_args[0] == ("POST", "calendar-service/event")
        body = call_args[1]["json"]
        assert body["eventName"] == "Jiaxing Marathon"
        assert body["date"] == "2026-11-22"
        assert body["completionTarget"]["value"] == 21.0975
        assert body["completionTarget"]["unit"] == "kilometer"
        assert body["eventCustomization"]["isPrimaryEvent"] is True
        assert body["eventCustomization"]["customGoal"]["value"] == 5525.0
        assert body["eventTimeLocal"]["startTimeHhMm"] == "07:30"
        assert body["location"] == "Jiaxing"

    def test_add_event_validation_errors(self) -> None:
        assert "error" in add_event(name="", date="2026-11-22")
        assert "error" in add_event(name="Race", date="invalid-date")

    def test_add_event_api_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.client._run_request.side_effect = RuntimeError("network failed")
        res = add_event(name="Race", date="2026-11-22")
        assert "error" in res
        assert "network failed" in res["error"]


class TestDeleteEvent:
    def test_delete_event_success(self, mock_get_client: MagicMock) -> None:
        mock_get_client.client._run_request.return_value = MagicMock()
        res = delete_event(88888)
        assert res["ok"] is True
        assert res["event_id"] == 88888
        mock_get_client.client._run_request.assert_called_once_with("DELETE", "calendar-service/event/88888")

    def test_delete_event_invalid_id(self) -> None:
        assert "error" in delete_event("not-a-number")

    def test_delete_event_exception(self, mock_get_client: MagicMock) -> None:
        mock_get_client.client._run_request.side_effect = RuntimeError("not found")
        res = delete_event(88888)
        assert "error" in res
        assert "not found" in res["error"]
