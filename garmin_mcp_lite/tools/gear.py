from garmin_mcp_lite.client import get_client


def get_gear_list() -> dict:
    """获取装备库列表及里程信息。"""
    client = get_client()

    # 获取 userProfileNumber
    profile = client.get_user_profile()
    user_profile_number = profile.get("id")

    gear = client.get_gear(user_profile_number)
    items = []

    for g in gear:
        items.append({
            "id": g.get("uuid"),
            "name": g.get("customMakeModel", g.get("gearMakeName", "未知")),
            "type": g.get("gearTypeName"),
            "distance_km": round(g.get("distance", 0) / 1000, 1),
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
