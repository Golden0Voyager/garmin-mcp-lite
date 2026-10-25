"""One-command setup: verify both one-time logins, walk through what is missing.

Garmin is required — every tool reads it. The Mi Fitness login is only needed
for `garmin_sync_weight` and is skippable here, so users without a Xiaomi
scale can press Enter and move on.

Usage:
    garmin-mcp-lite-setup
    GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=... garmin-mcp-lite-setup
"""

from __future__ import annotations

import getpass
import os
import sys

from garmin_mcp_lite import xiaomi_login
from garmin_mcp_lite.login import LoginError, run_login
from garmin_mcp_lite.onboarding import probe_garmin, probe_xiaomi


def _ask_credentials() -> tuple[str, str]:
    email = os.environ.get("GARMIN_EMAIL") or input("    Garmin account (email): ").strip()
    password = os.environ.get("GARMIN_PASSWORD") or getpass.getpass("    Password (not echoed): ")
    return email, password


def _setup_garmin() -> bool:
    status = probe_garmin()
    if status["ok"]:
        print(f"✅ Garmin: logged in as {status['account']}")
        return True

    print(f"❌ Garmin: {status['detail']}")
    try:
        email, password = _ask_credentials()
        run_login(email, password)
        return True
    except LoginError as e:
        print(f"❌ {e}")
        if e.hint:
            print(e.hint)
        return False
    except KeyboardInterrupt:
        print("\nCancelled.")
        return False


def _setup_xiaomi() -> bool:
    status = probe_xiaomi()
    if status["ok"]:
        print("✅ Mi Fitness: token valid")
        return True

    answer = input(
        "    Use a Xiaomi/Mi body-fat scale (Mi Fitness)? Only needed for garmin_sync_weight. [y/N]: "
    ).strip().lower()
    if answer not in ("y", "yes"):
        print("    Skipped — every tool except garmin_sync_weight works without it.")
        return True
    # xiaomi_login.run() is the full interactive flow on purpose: it ends with
    # a report of what the cloud actually holds, which is what reveals a scale
    # bound to Zepp Life instead of Mi Fitness.
    return xiaomi_login.run() == 0


def main() -> int:
    print("=" * 62)
    print("garmin-mcp-lite setup")
    print("=" * 62)

    print("\n[1/2] Garmin Connect")
    if not _setup_garmin():
        return 1

    print("\n[2/2] Mi Fitness (optional)")
    try:
        if not _setup_xiaomi():
            return 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 1

    print("\nAll set. Point your MCP client at the server — see the README quickstart for")
    print("the exact config (e.g. `claude mcp add garmin -- garmin-mcp-lite`).")
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover - only reached when run as a script
