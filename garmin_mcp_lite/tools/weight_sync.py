"""Pull weigh-ins from Mi Fitness (小米运动健康) and fill the gaps in Garmin.

This is the only place in the package that reads from Xiaomi. It is a *sync*,
not an import: weighings Garmin already holds are left alone, so running it
twice is harmless and running it after a week offline catches up in one go.
That is also why it does not need a scheduler — the tool is cheap enough to call
whenever the assistant is already running.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict, as_list, days_ago_str, today_str
from garmin_mcp_lite.tools.body import _account_offset, _ms, _write_composition, get_body_composition
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

# The scale uploads the same weighing twice: a weight-only row, then the full
# body-composition row a few seconds later. Anything inside this window is one
# measurement reported twice, so the richer row wins instead of both being written.
_MERGE_WINDOW_S = 120

# How close a Garmin row has to be to a measurement to describe the same weighing.
# Wider than the merge window on purpose: the scale's two rows arrive seconds
# apart, but a row that made a round trip through Garmin can drift further.
_MATCH_WINDOW_S = 180


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


def _measurement_clock(record: dict[str, Any]) -> float:
    """The wall clock a weighing happened at, in Garmin's `date` frame.

    A Xiaomi timestamp carries no zone — it is the time on the clock in the room.
    Reading it as UTC rather than as the machine's local time is what makes
    matching independent of where the sync runs.
    """
    return datetime.fromisoformat(str(record["timestamp"])).replace(tzinfo=UTC).timestamp()


def _row_clock(row: dict[str, Any]) -> float | None:
    """The wall clock Garmin reports for a row, in the same frame as a Xiaomi one.

    Garmin returns two times per weigh-in and they are not the same thing: `date`
    is the local wall clock encoded as if it were UTC, `timestampGMT` the true
    instant. Only `date` is comparable to a Xiaomi timestamp without knowing the
    zone, so it is preferred and the instant is only the fallback.
    """
    wall = _ms(row.get("date"))
    if wall is not None:
        return wall
    instant = _ms(row.get("timestampGMT"))
    return None if instant is None else datetime.fromtimestamp(instant).replace(tzinfo=UTC).timestamp()


def _merge_duplicates(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Collapse the scale's double upload; keep every real weighing.

    A weight-only row followed by the full row seconds later is one measurement
    reported twice, so the richer row wins. Two weighings hours apart — morning
    fasted, evening before bed — are two measurements, and each gets its own entry
    on Garmin with its own timestamp.
    """
    merged: list[dict[str, Any]] = []
    collapsed = 0
    for record in sorted(records, key=lambda item: str(item["timestamp"])):
        previous = merged[-1] if merged else None
        if previous is not None and _gap(previous, record) <= _MERGE_WINDOW_S:
            if len(record) > len(previous):
                merged[-1] = record
            collapsed += 1
            continue
        merged.append(record)
    return merged, collapsed


def _gap(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Seconds between two Mi Fitness records."""
    first = datetime.fromisoformat(str(a["timestamp"]))
    second = datetime.fromisoformat(str(b["timestamp"]))
    return abs((first - second).total_seconds())


def _already_on_garmin(clocks: list[float | None], clock: float) -> bool:
    """Whether Garmin already holds this weighing.

    A row with no usable time can only be judged by its day, and treating it as
    "not this weighing" would write a duplicate on top of it — writing blind is
    the worse of the two failures.
    """
    if any(value is not None and abs(value - clock) <= _MATCH_WINDOW_S for value in clocks):
        return True
    return any(value is None for value in clocks)


def _window_clocks(client: Any, start: str, end: str) -> dict[str, list[float | None]]:
    """Wall-clock times of every weigh-in Garmin holds in the window, by day.

    `get_body_composition` collapses a day to a single row, so it cannot answer
    "is this weighing already there" once a day holds more than one. `get_weigh_ins`
    is the only view that shows all of them.
    """
    payload = as_dict(client.get_weigh_ins(start, end))
    days: dict[str, list[float | None]] = {}
    for summary in as_list(payload.get("dailyWeightSummaries")):
        for raw in as_list(as_dict(summary).get("allWeightMetrics")):
            row = as_dict(raw)
            day = str(row.get("calendarDate") or "")
            if day:
                days.setdefault(day, []).append(_row_clock(row))
    return days


def sync_weight(days: int = 7, dry_run: bool = False) -> dict:
    """Copy recent weigh-ins from the Xiaomi scale into Garmin Connect.

    Use this instead of `garmin_add_body_composition` when the measurement came
    from the Mi Fitness / Xiaomi body-fat scale — it reads the real values
    (weight, body fat, water, muscle, bone, BMI) rather than asking the user to
    type them.

    Every weighing becomes its own entry, with the time it was taken: morning
    fasted and evening before bed are two measurements, ten weighings make ten
    entries. Only the scale's double upload — a weight-only row followed by the
    full row seconds later — is folded into one, keeping the richer row.

    A weighing Garmin already holds (same moment within three minutes) is
    skipped, so re-running writes nothing. Matching is by moment rather than by
    day, which is what lets a second weighing on the same day through while still
    recognising the first.

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

    # Every weighing becomes its own entry. Only the scale's double upload — a
    # weight-only row followed by the full row seconds later — is folded into one.
    measurements, collapsed = _merge_duplicates(records)

    existing = get_body_composition(days=window, limit=window * 4)
    if "error" in existing:
        return {"error": f"Could not read Garmin body composition: {existing['error']}", "written": []}
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

    try:
        days_clocks = _window_clocks(client, days_ago_str(window), today_str())
    except Exception:
        # Older garminconnect has no get_weigh_ins. Fall back to the day summary,
        # which cannot tell one weighing from another, so an occupied day counts as
        # taken rather than risking a duplicate on top of an untimed row.
        days_clocks = {str(record.get("date")): [None] for record in existing.get("records", []) if record.get("date")}

    written: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    write_attempts = 0
    stopped_early: str | None = None

    for record in measurements:
        day = str(record["date"])
        clock = _measurement_clock(record)
        if _already_on_garmin(days_clocks.get(day, []), clock):
            skipped.append(
                {
                    "date": day,
                    "time": str(record["timestamp"]),
                    "reason": "already on Garmin",
                    "xiaomi_weight_kg": record["weight_kg"],
                }
            )
            continue

        reason = _implausibility(float(record["weight_kg"]), baseline)
        if reason is not None:
            # A refused entry is reported, never silently dropped; the user can
            # still write it deliberately via garmin_add_body_composition.
            skipped.append(
                {
                    "date": day,
                    "time": str(record["timestamp"]),
                    "reason": reason,
                    "xiaomi_weight_kg": record["weight_kg"],
                }
            )
            continue

        if dry_run:
            written.append(
                {"date": day, "time": str(record["timestamp"]), "weight_kg": record["weight_kg"], "would_write": True}
            )
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
                "time": str(record["timestamp"]),
                "weight_kg": record["weight_kg"],
                "verified": result.get("verified"),
                "body_fat_pct": record.get("body_fat_pct"),
            }
        )

    already = [item for item in skipped if item["reason"] == "already on Garmin"]
    summary: dict[str, Any] = {
        "dry_run": bool(dry_run),
        "window_days": window,
        "xiaomi": {
            "weigh_ins": len(records),
            "measurements": len(measurements),
            "days": len({str(item["date"]) for item in measurements}),
            "duplicates_merged": collapsed,
        },
        "garmin": {
            "weigh_ins_already_present": len(already),
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

    # Every write reads its own day back; a written-but-unverifiable entry usually
    # means the account's zone could not be read, which also means the next run
    # cannot see this entry and will write it again.
    unverified = [item for item in written if item.get("verified") is False]
    if unverified:
        summary["warning"] = (
            f"{len(unverified)} entr(ies) were written but could not be read back afterwards. If this repeats "
            "across runs, the account's timezone could not be calibrated from its own rows and duplicate "
            "entries may accumulate — check garmin.account_offset_hours before syncing again."
        )

    if not records:
        summary["note"] = (
            "Mi Fitness returned no weigh-ins in this window. If the app shows a history curve, "
            "the scale may be bound to Zepp Life instead — that is a different cloud and a "
            "different API, and nothing here can read it."
        )
    return summary
