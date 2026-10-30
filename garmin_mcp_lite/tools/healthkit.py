"""Pull weigh-ins that an iPhone Shortcut mirrored from Apple Health into Garmin.

Any scale whose app can write to Apple Health — Withings, Huawei Health, Yunmai,
Renpho — becomes a Garmin source through a file: a Shortcut automation appends
each new Health sample as one JSON line to a file in iCloud Drive, and this tool
reads that file and fills Garmin's gaps.

Confirm the app actually writes before setting any of this up. 蚂蚁阿福, the
scale this bridge was first built for, never does: its app has no sync switch
and Health lists no write access for it, so the bridge had nothing to read. The
write path is exactly the Xiaomi sync's — one entry per weighing, matched back
against Garmin by the moment it was taken, a plausibility gate before writing,
paced uploads, read-back verification — because undoing a bad weigh-in is
equally impossible whichever scale produced it.

The bridge file is append-only: this tool never edits or truncates it, so a
re-run is harmless and lines may repeat. One JSON object per line:

    {"timestamp": "2026-10-25T09:07:00", "weight_kg": 72.2, "body_fat_pct": 16.6}

`timestamp` is local time (what the Shortcut's Format Date produces); a bare
`date` without a time is read as 07:00, the same convention the manual write
tool uses. See the README's "Apple Health bridge" section for the Shortcut
recipe. Despite the .txt extension, each line is a JSON object.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import days_ago_str, today_str
from garmin_mcp_lite.tools.body import _account_offset, _write_composition, get_body_composition
from garmin_mcp_lite.tools.weight_sync import (
    _MAX_DAYS,
    _WRITE_PAUSE_S,
    _already_on_garmin,
    _baseline_weight,
    _implausibility,
    _measurement_clock,
    _merge_duplicates,
    _window_clocks,
)

# iCloud Drive's macOS mount point; the Shortcut appends to a file under a
# `garmin` folder there. The content is one JSON object per line, but the
# extension is .txt on purpose: Shortcuts' "Append to Text File" picker only
# enables recognized text types, and .jsonl shows up greyed out. Override with
# GARMIN_HEALTH_FILE for other setups.
DEFAULT_FILE = (
    Path.home()
    / "Library/Mobile Documents/com~apple~CloudDocs/garmin/weight.txt"
)

_OPTIONAL_FIELDS = (
    "body_fat_pct",
    "body_water_pct",
    "muscle_mass_kg",
    "bone_mass_kg",
    "bmi",
    "basal_met",
    "metabolic_age",
)


def _bridge_file() -> Path:
    return Path(os.environ.get("GARMIN_HEALTH_FILE", str(DEFAULT_FILE))).expanduser()


def _normalise(entry: Any) -> dict[str, Any] | None:
    """Validate one JSON line into the shape the sync writes, or None."""
    if not isinstance(entry, dict):
        return None
    weight = entry.get("weight_kg")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
        return None

    timestamp = str(entry.get("timestamp") or "").strip()
    day = str(entry.get("date") or "").strip() or timestamp[:10]
    if not timestamp:
        timestamp = f"{day}T07:00:00" if day else ""
    if not day or not timestamp:
        return None
    try:
        datetime.fromisoformat(timestamp)
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return None

    record: dict[str, Any] = {
        "timestamp": timestamp,
        "date": day,
        "weight_kg": round(float(weight), 2),
    }
    for field in _OPTIONAL_FIELDS:
        value = entry.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            record[field] = round(float(value), 2)
    return record


_DECODER = json.JSONDecoder()


def _decode_concatenated(text: str) -> list[Any]:
    """Split a line holding several glued-together JSON objects.

    Shortcuts' Append to Text File action adds no trailing newline, so a Text
    action that forgot the final line break glues the next measurement onto
    the same line. Decoding them back apart keeps that formatting slip from
    silently dropping weigh-ins; whatever prefix decodes is returned, and a
    line with nothing decodable comes back empty (counted as unparsed).
    """
    entries: list[Any] = []
    rest = text.strip()
    while rest:
        try:
            entry, end = _DECODER.raw_decode(rest)
        except json.JSONDecodeError:
            break
        entries.append(entry)
        rest = rest[end:].lstrip()
    return entries


def _read_bridge(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Parse the append-only file into records; count lines that had to be skipped."""
    records: list[dict[str, Any]] = []
    skipped = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            candidates = [json.loads(stripped)]
        except json.JSONDecodeError:
            candidates = _decode_concatenated(stripped)
            if not candidates:
                skipped += 1
                continue
        for entry in candidates:
            record = _normalise(entry)
            if record is None:
                skipped += 1
            else:
                records.append(record)
    return records, skipped


def sync_healthkit(days: int = 30, dry_run: bool = False) -> dict:
    """Copy weigh-ins bridged from Apple Health into Garmin Connect.

    Use this when the measurement came from a scale that is NOT bound to Mi
    Fitness but whose app writes to Apple Health. Not every app does: 蚂蚁阿福
    writes nothing at all, which is what the README's Step 0 check exists for.
    Requires the one-time iPhone Shortcut described in the README's "Apple
    Health bridge" section; the file it appends to is the only input.

    The same guarantees as `garmin_sync_weight`: every weighing becomes its own
    entry with the time it was taken (a morning and an evening weighing are two
    measurements, not one), a weighing Garmin already holds — same moment within
    three minutes — is skipped so re-runs write nothing, implausible weights are
    refused rather than written, writes are paced, and each write is confirmed by
    reading the day back. The only lines folded together are the scale's double
    upload, a weight-only row followed seconds later by the full one. `verified:
    false` entries raise the same timezone-mismatch warning.

    THIS WRITES TO YOUR GARMIN ACCOUNT unless `dry_run` is true. Call with
    `dry_run=true` first when the user has not seen the numbers yet.

    Args:
        days: How far back to look, in days. Defaults to 30, capped at 90.
        dry_run: Report what would be written without writing anything.
    """
    path = _bridge_file()
    if not path.exists():
        return {
            "error": (
                f"No Apple Health bridge file at {path}. On the iPhone, create the "
                "Shortcut from the README's 'Apple Health bridge' section and run it "
                "once after a weigh-in; or point GARMIN_HEALTH_FILE at the file you use."
            ),
            "written": [],
        }

    try:
        records, unparsed = _read_bridge(path)
    except OSError as exc:
        return {"error": f"Could not read the bridge file: {exc}", "written": []}

    # Identical timestamps are the same measurement appended twice.
    seen: set[str] = set()
    duplicates = 0
    unique: list[dict[str, Any]] = []
    for record in records:
        if record["timestamp"] in seen:
            duplicates += 1
        else:
            seen.add(record["timestamp"])
            unique.append(record)

    window = max(1, min(int(days), _MAX_DAYS))
    cutoff = (datetime.now() - timedelta(days=window)).strftime("%Y-%m-%d")
    in_window = [record for record in unique if record["date"] >= cutoff]

    # Every weighing becomes its own entry, the same rule as the Xiaomi sync:
    # morning and evening are two measurements. Only the same moment reported
    # twice — a shortcut triggered twice — is folded into one.
    measurements, collapsed = _merge_duplicates(in_window)

    existing = get_body_composition(days=window, limit=window * 4)
    if "error" in existing:
        return {"error": f"Could not read Garmin body composition: {existing['error']}", "written": []}
    baseline = _baseline_weight(existing)

    try:
        client = get_client()
    except Exception as exc:
        return {"error": str(exc), "written": []}

    try:
        offset_s = _account_offset(client, days_ago_str(window), today_str())
    except Exception:
        offset_s = None

    try:
        days_clocks = _window_clocks(client, days_ago_str(window), today_str())
    except Exception:
        days_clocks = {str(record.get("date")): [None] for record in existing.get("records", []) if record.get("date")}

    written: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    write_attempts = 0
    summary_stop: str | None = None

    for record in measurements:
        day = record["date"]
        clock = _measurement_clock(record)
        if _already_on_garmin(days_clocks.get(day, []), clock):
            skipped.append(
                {
                    "date": day,
                    "time": record["timestamp"],
                    "reason": "already on Garmin",
                    "weight_kg": record["weight_kg"],
                }
            )
            continue

        reason = _implausibility(float(record["weight_kg"]), baseline)
        if reason is not None:
            skipped.append(
                {"date": day, "time": record["timestamp"], "reason": reason, "weight_kg": record["weight_kg"]}
            )
            continue

        if dry_run:
            written.append(
                {"date": day, "time": record["timestamp"], "weight_kg": record["weight_kg"], "would_write": True}
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
                # Same reasoning as the Xiaomi sync: hammering a rate limit only
                # lengthens the block, and stopping is safe because a weighing
                # already on Garmin is skipped next time.
                summary_stop = (
                    f"Garmin rate-limited the run after {len(written)} writes. Nothing is lost — "
                    "re-run in a few minutes and it continues from there."
                )
                break
            continue
        written.append(
            {
                "date": day,
                "time": record["timestamp"],
                "weight_kg": record["weight_kg"],
                "verified": result.get("verified"),
                "body_fat_pct": record.get("body_fat_pct"),
            }
        )

    already = [item for item in skipped if item["reason"] == "already on Garmin"]
    summary: dict[str, Any] = {
        "dry_run": bool(dry_run),
        "window_days": window,
        "file": str(path),
        "bridge": {
            "lines": len(records) + unparsed,
            "parsed": len(records),
            "unparsed": unparsed,
            "duplicate_timestamps": duplicates,
            "measurements": len(measurements),
            "days": len({str(item["date"]) for item in measurements}),
            "duplicates_merged": collapsed,
        },
        "garmin": {
            "weigh_ins_already_present": len(already),
            "plausibility_baseline_kg": baseline,
            "account_offset_hours": None if offset_s is None else round(offset_s / 3600, 2),
        },
        "written": written,
        "skipped": skipped,
        "failed": failed,
    }
    if summary_stop:
        summary["stopped_early"] = summary_stop

    unverified = [item for item in written if item.get("verified") is False]
    if unverified:
        summary["warning"] = (
            f"{len(unverified)} entr(ies) were written but could not be read back afterwards. If this repeats "
            "across runs, the account's timezone could not be calibrated from its own rows and duplicate "
            "entries may accumulate — check garmin.account_offset_hours before syncing again."
        )

    if not measurements and not skipped:
        summary["note"] = (
            "The bridge file holds no weigh-ins in this window. Weigh in, let the 阿福 app sync to Apple "
            "Health, then run the Shortcut (or check that its automation is enabled and the file path matches)."
        )
    return summary
