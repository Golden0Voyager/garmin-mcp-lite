"""Shared login probes and next-step instructions.

The `garmin_status` tool reports these probes to the assistant; the
`garmin-mcp-lite-setup` command drives them interactively. Both live here so
the wording of "what to run next" cannot drift between the two.
"""

from __future__ import annotations

from typing import Any

from garmin_mcp_lite.client import TOKEN_FILE, get_client
from garmin_mcp_lite.xiaomi import TOKEN_PATH, MiCloud, XiaomiError, load_token, save_token

GARMIN_LOGIN_CMD = "GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=xxx garmin-mcp-lite-login"
XIAOMI_LOGIN_CMD = "garmin-mcp-lite-xiaomi-login"
SETUP_CMD = "garmin-mcp-lite-setup"


def probe_garmin() -> dict[str, Any]:
    """Try to establish a Garmin session from the cached token. Never raises."""
    result: dict[str, Any] = {
        "ok": False,
        "token_file": str(TOKEN_FILE),
        "next": GARMIN_LOGIN_CMD,
    }
    if not TOKEN_FILE.exists():
        result["detail"] = f"No Garmin token at {TOKEN_FILE} — the login command has not been run yet."
        return result
    try:
        account = get_client().get_full_name()
    except Exception as e:
        # get_client() wraps the common failures in a RuntimeError that already
        # names the command to re-run, so pass the text through untouched.
        result["detail"] = str(e)
        return result
    result.update({"ok": True, "next": None, "account": str(account), "detail": "token valid"})
    return result


def probe_xiaomi() -> dict[str, Any]:
    """Validate the Mi Fitness token, rotating and re-saving it. Never raises."""
    result: dict[str, Any] = {
        "ok": False,
        "optional": True,
        "needed_for": "garmin_sync_weight",
        "token_file": str(TOKEN_PATH),
        "next": XIAOMI_LOGIN_CMD,
    }
    token = load_token()
    if token is None:
        result["detail"] = f"No Mi Fitness token at {TOKEN_PATH} — the Xiaomi login command has not been run."
        return result
    try:
        cloud = MiCloud(token)
        # refresh() rotates the token, so persist the new one exactly like
        # fetch_weights() does on every sync.
        save_token(cloud.refresh())
    except XiaomiError as e:
        # The message already says to run `garmin-mcp-lite-xiaomi-login` again.
        result["detail"] = str(e)
        return result
    except Exception as e:  # network, DNS, TLS — worth reporting, never worth raising
        result["detail"] = f"Could not reach Mi Fitness: {e}"
        return result
    result.update({"ok": True, "next": None, "detail": "token valid"})
    return result
