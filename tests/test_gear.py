from __future__ import annotations

from garmin_mcp_lite.tools.gear import get_gear_list


class TestGetGearList:
    def test_returns_gear(self) -> None:
        result = get_gear_list()
        assert result["count"] == 1
        item = result["gear"][0]
        assert item["name"] == "Nike Vaporfly 3"
        assert item["distance_km"] == 450.0
        assert item["retired"] is False
