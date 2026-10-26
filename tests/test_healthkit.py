"""Tests for the Apple Health bridge sync (garmin_sync_healthkit).

The bridge file is user-shaped data appended by an iPhone Shortcut, so the
tests focus on what the tool refuses to do with malformed, duplicated or
implausible input — the same guarantees as the Xiaomi sync, which share the
plausibility gate.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from garmin_mcp_lite.tools import healthkit


@pytest.fixture()
def bridge_file(monkeypatch: pytest.MonkeyPatch) -> Path:
    path = Path(tempfile.mkdtemp(dir="/tmp")) / "weight.txt"
    monkeypatch.setattr(healthkit, "_bridge_file", lambda: path)
    yield path
    shutil.rmtree(path.parent, ignore_errors=True)


def _line(day: str, weight: float = 72.2, time: str = "09:00:00", **extra) -> str:
    return json.dumps({"timestamp": f"{day}T{time}", "weight_kg": weight, "source": "afu", **extra})


def _garmin_history(days_weights: dict[str, float]) -> dict:
    return {"records": [{"date": day, "weight_kg": w} for day, w in days_weights.items()]}


@pytest.fixture()
def mocks():
    with (
        patch.object(healthkit, "get_body_composition") as read,
        patch.object(healthkit, "add_body_composition") as write,
        patch.object(healthkit.time, "sleep"),
    ):
        read.return_value = {"records": []}
        write.return_value = {"written": True, "verified": True}
        yield read, write


class TestMissingFile:
    def test_names_the_file_and_points_at_the_readme(self, bridge_file: Path, mocks) -> None:
        result = healthkit.sync_healthkit()
        assert str(bridge_file) in result["error"]
        assert "Apple Health bridge" in result["error"]
        assert result["written"] == []


class TestParsing:
    def test_env_var_overrides_the_file_location(self, monkeypatch: pytest.MonkeyPatch) -> None:
        custom = Path("/tmp/garmin-bridge-test/custom.jsonl")
        monkeypatch.setenv("GARMIN_HEALTH_FILE", str(custom))
        assert healthkit._bridge_file() == custom

    def test_skips_garbage_lines_and_duplicate_timestamps(self, bridge_file: Path, mocks) -> None:
        read, write = mocks
        bridge_file.write_text(
            "\n".join(
                [
                    "not json at all",
                    json.dumps({"date": "2026-10-25"}),  # no weight
                    _line("2026-10-25", 72.2),
                    _line("2026-10-25", 72.2),  # same measurement appended twice
                    _line("2026-10-24", 71.9),
                ]
            ),
            encoding="utf-8",
        )

        result = healthkit.sync_healthkit()

        assert result["bridge"]["lines"] == 5
        assert result["bridge"]["parsed"] == 3
        assert result["bridge"]["unparsed"] == 2
        assert result["bridge"]["duplicate_timestamps"] == 1
        assert result["bridge"]["days"] == 2
        assert write.call_count == 2

    def test_glued_objects_without_a_trailing_newline_are_split_apart(self, bridge_file: Path, mocks) -> None:
        # Shortcuts' append action adds no newline, so a Text action that
        # forgot the final line break produces one line with two objects.
        _read, write = mocks
        bridge_file.write_text(
            _line("2026-10-24", 71.9) + _line("2026-10-25", 72.2),
            encoding="utf-8",
        )

        result = healthkit.sync_healthkit()

        assert result["bridge"]["unparsed"] == 0
        assert result["bridge"]["days"] == 2
        assert write.call_count == 2

    def test_glued_line_with_trailing_garbage_keeps_what_decoded(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(
            _line("2026-10-24", 71.9) + "garbage{",
            encoding="utf-8",
        )

        result = healthkit.sync_healthkit()

        assert result["bridge"]["days"] == 1
        assert write.call_count == 1
        assert write.call_args.kwargs["weight"] == 71.9

    def test_date_only_line_is_read_as_7am(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(
            json.dumps({"date": "2026-10-25", "weight_kg": 72.2}), encoding="utf-8"
        )

        healthkit.sync_healthkit()

        assert write.call_args.kwargs["date"] == "2026-10-25T07:00:00"

    def test_bad_timestamp_line_is_skipped(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(
            json.dumps({"date": "25/10/2026", "weight_kg": 72.2}), encoding="utf-8"
        )

        result = healthkit.sync_healthkit()

        assert result["bridge"]["days"] == 0
        write.assert_not_called()

    def test_skips_non_dict_and_blank_and_dateless_lines(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(
            "\n".join(
                [
                    "[1, 2]",  # valid JSON, but not an object
                    "",  # blank line
                    json.dumps({"weight_kg": 70.0}),  # no timestamp and no date
                    _line("2026-10-25", 72.2),
                ]
            ),
            encoding="utf-8",
        )

        result = healthkit.sync_healthkit()

        # The blank line is skipped silently; the other two are reported.
        assert result["bridge"]["unparsed"] == 2
        assert result["bridge"]["days"] == 1
        write.assert_called_once()

    def test_unreadable_file_is_reported(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(_line("2026-10-25"), encoding="utf-8")

        def boom(*args, **kwargs) -> str:
            raise OSError("icloud not mounted")

        with patch.object(Path, "read_text", side_effect=boom):
            result = healthkit.sync_healthkit()

        assert "icloud not mounted" in result["error"]
        write.assert_not_called()

    def test_optional_fields_are_forwarded(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(
            json.dumps(
                {
                    "date": "2026-10-25",
                    "weight_kg": 72.2,
                    "body_fat_pct": 16.6,
                    "muscle_mass_kg": 30.1,
                    "bmi": 22.9,
                }
            ),
            encoding="utf-8",
        )

        healthkit.sync_healthkit()

        kwargs = write.call_args.kwargs
        assert kwargs["body_fat"] == 16.6
        assert kwargs["muscle_mass"] == 30.1
        assert kwargs["bmi"] == 22.9
        assert kwargs["bone_mass"] is None


class TestWindow:
    def test_old_days_outside_the_window_are_ignored(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        old = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        recent = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        bridge_file.write_text("\n".join([_line(old, 70.0), _line(recent, 72.0)]), encoding="utf-8")

        result = healthkit.sync_healthkit(days=30)

        assert result["bridge"]["days"] == 1
        assert write.call_args.kwargs["weight"] == 72.0

    def test_window_is_capped_at_90(self, bridge_file: Path, mocks) -> None:
        _read, _write = mocks
        bridge_file.write_text("", encoding="utf-8")

        result = healthkit.sync_healthkit(days=1000)

        assert result["window_days"] == healthkit._MAX_DAYS


class TestSyncSemantics:
    def test_skips_days_garmin_already_has(self, bridge_file: Path, mocks) -> None:
        read, write = mocks
        bridge_file.write_text(_line("2026-10-25"), encoding="utf-8")
        read.return_value = _garmin_history({"2026-10-25": 72.2})

        result = healthkit.sync_healthkit()

        assert result["skipped"][0]["reason"] == "already on Garmin"
        write.assert_not_called()

    def test_refuses_implausible_weight_before_writing(self, bridge_file: Path, mocks) -> None:
        read, write = mocks
        bridge_file.write_text(_line("2026-10-25", 145.0), encoding="utf-8")
        read.return_value = _garmin_history({"2026-10-22": 71.8, "2026-10-23": 72.0, "2026-10-24": 71.9})

        result = healthkit.sync_healthkit()

        assert result["written"] == []
        assert "unit mix-up" in result["skipped"][0]["reason"]
        assert result["garmin"]["plausibility_baseline_kg"] == 71.9
        write.assert_not_called()

    def test_keeps_only_the_earliest_weigh_in_of_a_day(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(
            "\n".join([_line("2026-10-25", 72.4, time="21:30:00"), _line("2026-10-25", 72.2, time="07:10:00")]),
            encoding="utf-8",
        )

        result = healthkit.sync_healthkit()

        assert result["bridge"]["same_day_collapsed"] == 1
        assert write.call_args.kwargs["weight"] == 72.2

    def test_collapses_later_weigh_ins_that_arrive_in_order(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        # Chronological order exercises the other collapse branch: the day is
        # already set by an earlier record and the later one is folded away.
        bridge_file.write_text(
            "\n".join([_line("2026-10-25", 72.2, time="07:10:00"), _line("2026-10-25", 72.4, time="21:30:00")]),
            encoding="utf-8",
        )

        result = healthkit.sync_healthkit()

        assert result["bridge"]["same_day_collapsed"] == 1
        assert write.call_args.kwargs["weight"] == 72.2

    def test_dry_run_writes_nothing(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(_line("2026-10-25"), encoding="utf-8")

        result = healthkit.sync_healthkit(dry_run=True)

        assert result["dry_run"] is True
        assert result["written"][0]["would_write"] is True
        write.assert_not_called()

    def test_garmin_read_failure_aborts_before_writing(self, bridge_file: Path, mocks) -> None:
        read, write = mocks
        bridge_file.write_text(_line("2026-10-25"), encoding="utf-8")
        read.return_value = {"error": "401"}

        result = healthkit.sync_healthkit()

        assert "401" in result["error"]
        write.assert_not_called()

    def test_records_a_failed_write(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(_line("2026-10-25"), encoding="utf-8")
        write.return_value = {"error": "upload refused", "written": False}

        result = healthkit.sync_healthkit()

        assert result["written"] == []
        assert result["failed"] == [{"date": "2026-10-25", "error": "upload refused"}]

    def test_unverified_writes_raise_the_timezone_warning(self, bridge_file: Path, mocks) -> None:
        _read, write = mocks
        bridge_file.write_text(_line("2026-10-25"), encoding="utf-8")
        write.return_value = {"written": True, "verified": False}

        result = healthkit.sync_healthkit()

        assert "timezone" in result["warning"]

    def test_empty_window_gets_a_hint(self, bridge_file: Path, mocks) -> None:
        _read, _write = mocks
        bridge_file.write_text("", encoding="utf-8")

        result = healthkit.sync_healthkit()

        assert "Shortcut" in result["note"]
