"""Interactive Mi Fitness login, plus a report of what the cloud actually holds.

Run this once. It needs a captcha and possibly an SMS/email code, so it cannot
be a tool call — afterwards ``garmin_sync_weight`` reuses the cached token.

Usage:
    garmin-mcp-lite-xiaomi-login
    XIAOMI_USER=you@example.com XIAOMI_PASSWORD=... garmin-mcp-lite-xiaomi-login
    garmin-mcp-lite-xiaomi-login --relogin --days 90

The report is deliberately part of this command: if the scale is bound to Zepp
Life instead of Mi Fitness, the data lives in a different cloud and the sync
tool would report "nothing to sync" forever. Seeing the record count here makes
that visible immediately.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import webbrowser
from datetime import datetime, timedelta

from garmin_mcp_lite.xiaomi import (
    TOKEN_PATH,
    MiCloud,
    MiLogin,
    XiaomiError,
    load_token,
    save_token,
)


def _report(records: list[dict]) -> None:
    if not records:
        print("\n  No weight records in this account.")
        print("  Check, in order:")
        print("    1. Mi Fitness app -> Health -> Weight: is there a history curve?")
        print("    2. If yes here but empty above, the scale is bound to Zepp Life and")
        print("       the data lives in api-mifit.zepp.com, a different API entirely.")
        print("    3. If both are empty, the scale was never bound to this account.")
        return

    first = datetime.fromisoformat(records[0]["timestamp"]).strftime("%Y-%m-%d %H:%M")
    last = datetime.fromisoformat(records[-1]["timestamp"]).strftime("%Y-%m-%d %H:%M")
    print(f"  records: {len(records)}")
    print(f"  range:   {first} -> {last}")

    sources: dict[str, int] = {}
    for record in records:
        sources[record["source"]] = sources.get(record["source"], 0) + 1
    ranked = sorted(sources.items(), key=lambda pair: -pair[1])
    print("  sources: " + ", ".join(f"{name} ({count})" for name, count in ranked))

    with_fat = sum(1 for record in records if "body_fat_pct" in record)
    print(f"  body fat present on {with_fat}/{len(records)} records")

    print("\n  latest 5:")
    for record in records[-5:]:
        moment = datetime.fromisoformat(record["timestamp"]).strftime("%Y-%m-%d %H:%M")
        parts = [f"{record['weight_kg']:.2f} kg"]
        if "body_fat_pct" in record:
            parts.append(f"fat {record['body_fat_pct']:.1f}%")
        if "bmi" in record:
            parts.append(f"BMI {record['bmi']:.1f}")
        print(f"    {moment}  " + "  ".join(parts) + f"  [{record['source']}]")


def run(days: int = 30, relogin: bool = False) -> int:
    """The whole login / data-check flow; returns a process exit code."""
    print("=" * 62)
    print("Mi Fitness login / data check")
    print("=" * 62)

    token = None if relogin else load_token()
    cloud: MiCloud | None = None

    if token is not None:
        print(f"\n[1/2] Reusing cached token: {TOKEN_PATH}")
        cloud = MiCloud(token)
        try:
            token = cloud.refresh()
            print("      token still valid")
        except XiaomiError as exc:
            print(f"      {exc}")
            cloud = None

    if cloud is None:
        print("\n[1/2] Logging in to Mi Fitness (sid=miothealth)")
        username = os.environ.get("XIAOMI_USER") or input("    Xiaomi account (phone/email): ").strip()
        password = os.environ.get("XIAOMI_PASSWORD") or getpass.getpass("    Password (not echoed): ")

        login = MiLogin()

        def on_captcha(path) -> None:
            print(f"    Captcha image: {path}")
            webbrowser.open(f"file://{path}")

        token = login.login(username, password, on_captcha=on_captcha)
        cloud = MiCloud(token)
        cloud.refresh()
        print(f"      logged in as {token['userId'][:4]}****")

    print(f"\n[2/2] Reading weight data (last {days} days)")
    try:
        records = cloud.fetch_weight_records()
    except XiaomiError as exc:
        print(f"      failed: {exc}")
        return 1

    cutoff = datetime.now() - timedelta(days=max(1, days))
    recent = [record for record in records if datetime.fromisoformat(record["timestamp"]) >= cutoff]
    print(f"      {len(records)} records total, {len(recent)} inside the window\n")
    # Fall back to the full history: an empty window is not the same as an empty account.
    _report(recent or records)

    save_token(cloud.token)
    print(f"\ntoken saved: {TOKEN_PATH} (mode 600)")
    print("\nNext: ask the assistant to run garmin_sync_weight, or call it with dry_run=true first.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Log in to Mi Fitness and report the weight data it holds.")
    parser.add_argument("--days", type=int, default=30, help="How many days of history to report (default 30)")
    parser.add_argument("--relogin", action="store_true", help="Ignore the cached token and log in again")
    args = parser.parse_args()
    return run(days=args.days, relogin=args.relogin)


if __name__ == "__main__":
    sys.exit(main())
