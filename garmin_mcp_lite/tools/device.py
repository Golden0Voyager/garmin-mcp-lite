from garmin_mcp_lite.client import get_client


def get_device_info() -> dict:
    """获取已连接设备信息及同步状态。"""
    client = get_client()

    devices = client.get_devices()
    result = []

    for d in devices:
        result.append({
            "id": d.get("deviceId"),
            "name": d.get("productDisplayName"),
            "model": d.get("partNumber"),
            "software_version": d.get("softwareVersion"),
            "last_sync": d.get("lastSyncTime"),
            "battery_level": d.get("batteryStatus"),
            "connected": d.get("connected", False),
        })

    return {
        "count": len(result),
        "devices": result,
    }
