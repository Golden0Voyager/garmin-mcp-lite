from __future__ import annotations

from garmin_mcp_lite.tools.events import get_events


class TestGetEvents:
    def test_returns_events(self) -> None:
        result = get_events()
        assert result["count"] == 1
        event = result["events"][0]
        assert event["name"] == "Tokyo Marathon"
        assert event["distance_km"] == 42.195
        assert event["goal_time"] == "4:00:00"
