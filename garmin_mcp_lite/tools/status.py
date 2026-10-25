from garmin_mcp_lite.onboarding import probe_garmin, probe_xiaomi


def get_status() -> dict:
    """Check whether the one-time logins are in place before using the other tools.

    Every other tool needs a Garmin token (one-time `garmin-mcp-lite-login`);
    only `garmin_sync_weight` additionally needs a Mi Fitness token (one-time
    `garmin-mcp-lite-xiaomi-login`, captcha + SMS, so it cannot happen from a
    tool call). Call this first when a tool failed with an auth error, or when
    you are unsure which setup steps remain: each side reports `ok`, what is
    wrong (`detail`), and the exact command to run next (`next`, null when
    nothing is needed).

    `ready` reflects the Garmin side only — a missing Xiaomi token is normal
    when the user has no Xiaomi scale and does not limit any tool except
    `garmin_sync_weight`.
    """
    garmin = probe_garmin()
    xiaomi = probe_xiaomi()
    return {
        "garmin": garmin,
        "xiaomi": xiaomi,
        "ready": bool(garmin["ok"]),
    }
