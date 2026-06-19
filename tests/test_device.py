from __future__ import annotations

from garmin_mcp_lite.tools.device import get_device_info


class TestGetDeviceInfo:
    def test_returns_devices(self) -> None:
        result = get_device_info()
        assert result["count"] == 1
        dev = result["devices"][0]
        assert dev["name"] == "My Fenix 7"
        assert dev["firmware_version"] == "28.10"
        assert dev["is_primary_tracker"] is True
