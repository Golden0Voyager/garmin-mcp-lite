from datetime import datetime

from garmin_mcp_lite.client import get_client


def get_challenges() -> dict:
    """Get in-progress challenges and badge completion status, including virtual challenges and monthly badges."""
    client = get_client()
    now = datetime.now()

    result = {
        "virtual_challenges": [],
        "badge_challenges": [],
    }

    # 1. Virtual challenges (climbing, hiking, etc.)
    try:
        virtual = client.get_inprogress_virtual_challenges(1, 50)
        for v in virtual:
            progress = v.get("badgeProgressValue", 0)
            target = v.get("badgeTargetValue", 0)
            percent = round((progress / target * 100), 1) if target > 0 else 0

            result["virtual_challenges"].append({
                "name": v.get("badgeChallengeName"),
                "progress": progress,
                "target": target,
                "percentage": percent,
                "points": v.get("badgePoints"),
            })
    except Exception:
        pass

    # 2. Badge challenges (monthly challenges, etc.)
    try:
        badges = client.get_badge_challenges(1, 100)
        for b in badges:
            start_str = b.get("startDate")
            end_str = b.get("endDate")
            if not (start_str and end_str):
                continue

            start = datetime.fromisoformat(start_str.split("T")[0])
            end = datetime.fromisoformat(end_str.split("T")[0])

            # Only include active and joined challenges
            if start <= now <= end and b.get("userJoined"):
                progress = b.get("badgeProgressValue", 0)
                target = b.get("badgeTargetValue", 0)

                # Unit conversion (Garmin internally uses meters, seconds, etc.)
                unit_id = b.get("badgeUnitId")
                unit_name = "units"
                if unit_id == 1: # Distance (meters)
                    progress = round(progress / 1000, 2)
                    target = round(target / 1000, 2)
                    unit_name = "km"
                elif unit_id == 7: # Time (seconds)
                    progress = round(progress / 3600, 1)
                    target = round(target / 3600, 1)
                    unit_name = "hours"

                percent = round((progress / target * 100), 1) if target > 0 else 0

                result["badge_challenges"].append({
                    "name": b.get("badgeChallengeName"),
                    "progress": progress,
                    "target": target,
                    "unit": unit_name,
                    "percentage": percent,
                    "end_date": end_str.split("T")[0],
                    "points": b.get("badgePoints"),
                })
    except Exception:
        pass

    return result
