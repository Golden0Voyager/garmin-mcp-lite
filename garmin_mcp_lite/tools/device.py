from datetime import datetime
from garmin_mcp_lite.client import get_client


def get_device_info() -> dict:
    """Get connected device information including firmware version, update availability, primary tracker role, and registration date."""
    client = get_client()

    devices = client.get_devices()
    result = []

    for d in devices:
        # 注册日期转换
        reg_date = d.get("registeredDate")
        reg_date_str = None
        if reg_date:
            reg_date_str = datetime.fromtimestamp(reg_date / 1000).strftime('%Y-%m-%d')

        result.append({
            "id": d.get("deviceId"),
            "name": d.get("displayName") or d.get("productDisplayName"),
            "model": d.get("partNumber"),
            "firmware_version": d.get("currentFirmwareVersion"),
            "has_update": d.get("softwareUpdates") is not None and len(d.get("softwareUpdates", [])) > 0,
            "status": d.get("deviceStatus"),
            "is_primary_tracker": d.get("primaryActivityTrackerIndicator", False),
            "is_primary_training": d.get("primaryTrainingCapable", False),
            "registered_date": reg_date_str,
            "connected": d.get("connected", False),
        })

    return {
        "count": len(result),
        "devices": result,
    }
