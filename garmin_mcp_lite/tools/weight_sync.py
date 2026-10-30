"""Pull weigh-ins from Mi Fitness (小米运动健康) and fill the gaps in Garmin.

This is the only place in the package that reads from Xiaomi. It is a *sync*,
not an import: days that already have a Garmin entry are left alone, so running
it twice is harmless and running it after a week offline catches up in one go.
That is also why it does not need a scheduler — the tool is cheap enough to call
whenever the assistant is already running.
"""

from __future__ import annotations

import time
from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import days_ago_str, today_str
from garmin_mcp_lite.tools.body import _account_offset, _write_composition, get_body_composition
from garmin_mcp_lite.xiaomi import XiaomiError, fetch_weights

# Each write costs three API calls (write, status probe, read-back), so a long
# backfill is slow and pointless: Garmin's own chart is only useful recently.
_MAX_DAYS = 90

# A first backfill is ~90 writes in one tool call; without a pause that is a
# burst Garmin answers with a 429 (which then locks the IP for hours — the
# README's own troubleshooting explains this). Half a second keeps a 90-day
# backfill under a minute while spreading the load.
_WRITE_PAUSE_S = 0.5

# Implausible weights are refused rather than written, because a written entry
# cannot be undone. With ≥3 Garmin weights inside the window the reference is
# the median of those (a 斤 mis-read is exactly 2× kg, far outside ±40%);
# without history any absolute outlier is refused instead.
_MAX_DEVIATION = 0.40
_ABS_MIN_KG = 30.0
_ABS_MAX_KG = 250.0


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _baseline_weight(existing: dict[str, Any]) -> float | None:
    """Median of the Garmin weights already inside the window, once there are enough."""
    weights = [
        float(record["weight_kg"])
        for record in existing.get("records", [])
        if isinstance(record.get("weight_kg"), (int, float)) and not isinstance(record.get("weight_kg"), bool)
    ]
    if len(weights) < 3:
        return None
    return round(_median(weights), 1)


def _implausibility(weight: float, baseline: float | None) -> str | None:
    """Why this weight must not be written, or None when it is plausible."""
    if baseline is not None and abs(weight - baseline) / baseline > _MAX_DEVIATION:
        return (
            f"{weight} kg is far from the recent Garmin median {baseline} kg — "
            "looks like a unit mix-up (斤 reads exactly 2× kg) or a bad reading"
        )
    if baseline is None and not _ABS_MIN_KG <= weight <= _ABS_MAX_KG:
        return (
            f"{weight} kg is outside {_ABS_MIN_KG:.0f}–{_ABS_MAX_KG:.0f} kg and there is no Garmin "
            "history to judge it against — looks like a unit mix-up or a bad reading"
        )
    return None


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

    Weights that look wrong are refused, because Garmin keeps every entry and
    there is no undo: with ≥3 Garmin weigh-ins in the window, anything more
    than ±40% off their median is skipped (a 斤 mis-read is exactly 2× kg);
    without Garmin history, weights outside 30–250 kg are skipped. Skips are
    listed with the reason — override one manually with
    `garmin_add_body_composition` if it was genuine.

    Deleting a weigh-in in the Mi Fitness app does NOT remove it from Garmin:
    this tool has no delete path. Remove stray entries in the Garmin Connect
    app itself.

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
    baseline = _baseline_weight(existing)

    # Where the account's clock sits, read off the rows already there. This is
    # what keeps a sync run from a laptop in another timezone from filing every
    # weighing at the wrong hour — and from then failing to match it. One extra
    # read of the same window: get_body_composition() normalises the rows and
    # drops the raw pair the offset is computed from.
    try:
        client = get_client()
    except Exception as exc:
        # Everything else here reports failure as a dict; a missing Garmin token
        # must not be the one thing that throws instead.
        return {"error": str(exc), "written": []}

    try:
        offset_s = _account_offset(client, days_ago_str(window), today_str())
    except Exception:
        # An unreadable offset is not a reason to abandon the sync: without it the
        # timestamp is left alone, which is what every version before this did.
        offset_s = None

    written: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    write_attempts = 0
    stopped_early: str | None = None

    for day in sorted(by_day):
        record = by_day[day]
        if day in have:
            skipped.append({"date": day, "reason": "already on Garmin", "xiaomi_weight_kg": record["weight_kg"]})
            continue

        reason = _implausibility(float(record["weight_kg"]), baseline)
        if reason is not None:
            # A refused entry is reported, never silently dropped; the user can
            # still write it deliberately via garmin_add_body_composition.
            skipped.append({"date": day, "reason": reason, "xiaomi_weight_kg": record["weight_kg"]})
            continue

        if dry_run:
            written.append({"date": day, "weight_kg": record["weight_kg"], "would_write": True})
            continue

        if write_attempts:
            time.sleep(_WRITE_PAUSE_S)
        write_attempts += 1

        result = _write_composition(
            client,
            value=record["weight_kg"],
            timestamp=str(record["timestamp"]),
            body_fat=record.get("body_fat_pct"),
            body_water=record.get("body_water_pct"),
            muscle_mass=record.get("muscle_mass_kg"),
            bone_mass=record.get("bone_mass_kg"),
            bmi=record.get("bmi"),
            basal_met=record.get("basal_met"),
            metabolic_age=int(record["metabolic_age"]) if record.get("metabolic_age") else None,
            account_offset_s=offset_s,
        )
        if result.get("error"):
            failed.append({"date": day, "error": result["error"]})
            if result.get("rate_limited"):
                # Every remaining write would hit the same wall, and hammering it
                # only lengthens the block. Stopping is safe precisely because the
                # sync is idempotent: the next call resumes where this one stopped.
                stopped_early = (
                    f"Garmin rate-limited the run after {len(written)} writes. Nothing is lost — "
                    "re-run in a few minutes and it continues from there, because every day "
                    "already on Garmin is skipped."
                )
                break
            continue
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
        "garmin": {
            "days_already_present": len(have & set(by_day)),
            "plausibility_baseline_kg": baseline,
            # Read off the account's own rows; null means the window proved
            # nothing and the timestamps were sent unchanged.
            "account_offset_hours": None if offset_s is None else round(offset_s / 3600, 2),
        },
        "written": written,
        "skipped": skipped,
        "failed": failed,
    }
    if stopped_early:
        summary["stopped_early"] = stopped_early

    # add_body_composition() reads the day back; a written-but-unverifiable day
    # usually means the server's timezone disagrees with the account's, which
    # also means the next run cannot see this entry and will write it again.
    unverified = [item for item in written if item.get("verified") is False]
    if unverified:
        summary["warning"] = (
            f"{len(unverified)} day(s) were written but could not be read back afterwards. If this repeats "
            "across runs, the machine running this server likely has a different timezone than the Garmin "
            "account, and duplicate entries may accumulate — align the timezones before syncing again."
        )

    if not records:
        summary["note"] = (
            "Mi Fitness returned no weigh-ins in this window. If the app shows a history curve, "
            "the scale may be bound to Zepp Life instead — that is a different cloud and a "
            "different API, and nothing here can read it."
        )
    return summary
