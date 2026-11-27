from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_list


def get_gear_list() -> dict:
    """Get the gear library (shoes, bikes, etc.) with real cumulative mileage for each item."""
    client = get_client()

    # Get userProfileNumber
    profile = client.get_user_profile()
    user_profile_number = profile.get("id")

    # get_gear is annotated as dict, but every supported library version
    # returns a list of gear objects.
    gear = as_list(client.get_gear(str(user_profile_number)))
    items = []

    for g in gear:
        uuid = g.get("uuid")
        distance_meters = 0

        # 获取该装备的详细统计信息（含累计里程）
        if uuid:
            try:
                stats = client.get_gear_stats(uuid)
                distance_meters = stats.get("totalDistance", 0)
            except Exception:
                distance_meters = 0

        items.append({
            "id": uuid,
            "name": g.get("customMakeModel") or g.get("gearMakeName") or "未知",
            "type": g.get("gearTypeName"),
            "distance_km": round(distance_meters / 1000, 1),
            "max_distance_km": (
                round(g.get("maximumMeters", 0) / 1000, 1)
                if g.get("maximumMeters")
                else None
            ),
            "retired": g.get("retired", False),
            "default": g.get("defaultGear", False),
        })

    return {
        "count": len(items),
        "gear": items,
    }
