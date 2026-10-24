"""Pull weigh-ins from Mi Fitness (小米运动健康) and fill the gaps in Garmin.

This is the only place in the package that reads from Xiaomi. It is a *sync*,
not an import: days that already have a Garmin entry are left alone, so running
it twice is harmless and running it after a week offline catches up in one go.
That is also why it does not need a scheduler — the tool is cheap enough to call
whenever the assistant is already running.
"""

from __future__ import annotations

from typing import Any

from garmin_mcp_lite.tools.body import add_body_composition, get_body_composition
from garmin_mcp_lite.xiaomi import XiaomiError, fetch_weights

# Each write costs three API calls (write, status probe, read-back), so a long
# backfill is slow and pointless: Garmin's own chart is only useful recently.
_MAX_DAYS = 90


def sync_weight(days: int = 7, dry_run: bool = False) -> dict:
    """Copy recent weigh-ins from the Xiaomi scale into Garmin Connect.

    Use this instead of `garmin_add_body_composition` when the measurement came
    from the Mi Fitness / Xiaomi body-fat scale — it reads the real values
    (weight, body fat, water, muscle, bone, BMI) rather than asking the user to
    type them.

    Only days that Garmin does not already have are written, so the call is
    idempotent: re-running it writes nothing. Days are compared by local date,
    and when a day holds several weigh-ins only the earliest (usually the
    morning one) is used.

    THIS WRITES TO YOUR GARMIN ACCOUNT unless `dry_run` is true. There is no
    undo through this tool. Call with `dry_run=true` first when the user has not
    seen the numbers yet, then report what would be written.

    Requires a one-time interactive login (`garmin-mcp-lite-xiaomi-login`),
    because Xiaomi's login needs a captcha and an SMS code. When the token is
    missing or expired the result carries an `error` explaining that, and no
    write happens.

    Args:
        days: How far back to look, in days. Defaults to 7, capped at 90.
        dry_run: Report what would be written without writing anything.
    """
    window = max(1, min(int(days), _MAX_DAYS))

    try:
        records = fetch_weights(window)
    except XiaomiError as exc:
        return {"error": str(exc), "written": []}
    except Exception as exc:  # network, DNS, TLS — all recoverable by retrying later
        return {"error": f"Could not read from Mi Fitness: {exc}", "written": []}

    # One entry per day: the earliest, which is the fasted morning weigh-in that
    # weight trends are actually about.
    by_day: dict[str, dict[str, Any]] = {}
    collapsed = 0
    for record in records:
        day = str(record["date"])
        current = by_day.get(day)
        if current is None:
            by_day[day] = record
        elif str(record["timestamp"]) < str(current["timestamp"]):
            by_day[day] = record
            collapsed += 1
        else:
            collapsed += 1

    existing = get_body_composition(days=window, limit=window * 4)
    if "error" in existing:
        return {"error": f"Could not read Garmin body composition: {existing['error']}", "written": []}
    have = {str(record.get("date")) for record in existing.get("records", []) if record.get("date")}

    written: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for day in sorted(by_day):
        record = by_day[day]
        if day in have:
            skipped.append({"date": day, "reason": "already on Garmin", "xiaomi_weight_kg": record["weight_kg"]})
            continue
        if dry_run:
            written.append({"date": day, "weight_kg": record["weight_kg"], "would_write": True})
            continue

        result = add_body_composition(
            weight=record["weight_kg"],
            date=str(record["timestamp"]),
            body_fat=record.get("body_fat_pct"),
            body_water=record.get("body_water_pct"),
            muscle_mass=record.get("muscle_mass_kg"),
            bone_mass=record.get("bone_mass_kg"),
            bmi=record.get("bmi"),
            basal_met=record.get("basal_met"),
            metabolic_age=int(record["metabolic_age"]) if record.get("metabolic_age") else None,
        )
        if result.get("error"):
            failed.append({"date": day, "error": result["error"]})
        else:
            written.append(
                {
                    "date": day,
                    "weight_kg": record["weight_kg"],
                    "verified": result.get("verified"),
                    "body_fat_pct": record.get("body_fat_pct"),
                }
            )

    summary: dict[str, Any] = {
        "dry_run": bool(dry_run),
        "window_days": window,
        "xiaomi": {"weigh_ins": len(records), "days": len(by_day), "same_day_collapsed": collapsed},
        "garmin": {"days_already_present": len(have & set(by_day))},
        "written": written,
        "skipped": skipped,
        "failed": failed,
    }
    if not records:
        summary["note"] = (
            "Mi Fitness returned no weigh-ins in this window. If the app shows a history curve, "
            "the scale may be bound to Zepp Life instead — that is a different cloud and a "
            "different API, and nothing here can read it."
        )
    return summary
