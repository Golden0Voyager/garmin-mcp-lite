from __future__ import annotations

import json
import logging
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from garmin_mcp_lite.tools import ledger as ledger_module
from garmin_mcp_lite.tools.ledger import (
    LedgerStore,
    _redact_text,
    _safe_error,
    collect_evening,
    collect_morning,
    configure_logging,
    main,
    read_ledger,
    render_markdown,
    run_ledger,
)


def _sleep_payload() -> dict:
    return {
        "dailySleepDTO": {
            "sleepScore": 82,
            "sleepScores": {"overall": {"value": 82, "qualifierKey": "GOOD"}},
            "sleepTimeInMinutes": 438,
            "deepSleepMinutes": 78,
            "lightSleepMinutes": 302,
            "remSleepMinutes": 58,
            "awakeSleepMinutes": 21,
            "restingHeartRate": 45,
        },
        "avgOvernightHrv": 58,
        "hrvStatus": "BALANCED",
    }


def _activity(activity_id: int, name: str, distance: float, duration: float) -> dict:
    return {
        "activityId": activity_id,
        "activityName": name,
        "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-11-27 07:30:00",
        "distance": distance,
        "duration": duration,
        "averageHR": 148,
        "maxHR": 172,
        "averageSpeed": 2.81,
    }


def _activity_detail(activity_id: int, load: float) -> dict:
    return {
        "activityName": f"Run {activity_id}",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "startTimeLocal": "2026-11-27 07:30:00",
            "distance": 5000,
            "duration": 1800,
            "averageHR": 148,
            "maxHR": 172,
            "averageSpeed": 2.78,
            "activityTrainingLoad": load,
            "trainingEffect": 3.0,
            "trainingEffectLabel": "IMPROVING_AEROBIC_FITNESS",
            "anaerobicTrainingEffect": 2.5,
        },
    }


class TestCollectMorning:
    def test_combines_hrv_and_sleep(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {
                "calendarDate": "2026-11-27",
                "status": "BALANCED",
                "weeklyAvg": 55,
                "lastNightAvg": 58,
                "baseline": {"balancedLow": 45, "balancedUpper": 65},
            }
        }
        mock_get_client.get_sleep_data.return_value = _sleep_payload()

        result = collect_morning("2026-11-27")

        assert result["status"] == "success"
        assert result["hrv"]["status"] == "BALANCED"
        assert result["sleep"]["duration_min"] == 438
        assert result["analysis"]["recovery_focus"] is False

    def test_marks_missing_hrv_as_failure(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {"hrvSummary": {}}
        mock_get_client.get_sleep_data.return_value = _sleep_payload()

        result = collect_morning("2026-11-27")

        assert result["status"] == "partial"
        assert result["hrv"]["status"] == "NO_DATA"
        assert result["errors"]

    def test_marks_sleep_error_as_failure(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {"calendarDate": "2026-11-27", "status": "BALANCED"}
        }
        mock_get_client.get_sleep_data.side_effect = RuntimeError("sleep down")

        result = collect_morning("2026-11-27")

        assert result["status"] == "partial"
        assert result["sleep"]["error"] == "sleep down"
        assert result["errors"] == ["sleep down"]

    def test_marks_unbalanced_hrv_as_recovery_focus(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {"calendarDate": "2026-11-27", "status": "UNBALANCED"}
        }
        mock_get_client.get_sleep_data.return_value = _sleep_payload()

        result = collect_morning("2026-11-27")

        assert result["analysis"]["recovery_focus"] is True


class TestCollectEvening:
    def test_aggregates_all_activities_without_limit(self, mock_get_client: MagicMock) -> None:
        activities = [
            _activity(1, "Morning Run", 5000, 1800),
            _activity(2, "Evening Run", 3000, 1200),
        ]
        mock_get_client.get_activities_by_date.return_value = activities
        mock_get_client.get_activity.side_effect = lambda activity_id: _activity_detail(
            int(activity_id), 50.0 if int(activity_id) == 1 else 30.0
        )

        result = collect_evening("2026-11-27")

        mock_get_client.get_activities_by_date.assert_any_call("2026-11-27", "2026-11-27")
        assert all("limit" not in call.kwargs for call in mock_get_client.get_activities_by_date.call_args_list)
        assert result["activity_count"] == 2
        assert result["totals"]["distance_km"] == 8.0
        assert result["totals"]["duration_min"] == 50
        assert result["totals"]["training_load"] == 80.0
        assert result["activities"][0]["training_load"] == 50.0

    def test_keeps_summary_when_detail_fails(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities_by_date.return_value = [_activity(1, "Morning Run", 5000, 1800)]
        mock_get_client.get_activity.side_effect = RuntimeError("detail down")

        result = collect_evening("2026-11-27")

        assert result["status"] == "partial"
        assert result["activity_count"] == 1
        assert result["activities"][0]["name"] == "Morning Run"
        assert result["activities"][0]["detail_error"] == "detail down"
        assert result["errors"] == ["activity 1: detail down"]
        assert result["totals"]["training_load"] is None
        assert result["totals"]["training_load_complete"] is False

    def test_labels_training_status_as_current(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities_by_date.return_value = []

        result = collect_evening("2026-11-27")

        current = result["training_status_current"]
        assert current["as_of"]
        assert current["training_status"] == "Productive"
        assert current["acute_load"] == 280
        assert result["activity_count"] == 0

    def test_activity_list_failure_is_unavailable(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities_by_date.side_effect = RuntimeError("activities down")

        result = collect_evening("2026-11-27")

        assert result["status"] == "unavailable"
        assert result["errors"] == ["activities down"]
        assert result["activities"] == []


class TestRunLedger:
    def test_rejects_unknown_mode(self) -> None:
        with pytest.raises(ValueError, match="Unsupported ledger mode"):
            run_ledger("weekly", "2026-11-27")  # type: ignore[arg-type]


def _morning_payload(marker: str = "first") -> dict:
    return {
        "date": "2026-11-27",
        "status": "success",
        "generated_at": "2026-11-27T10:00:00+08:00",
        "hrv": {"status": "BALANCED", "marker": marker},
        "sleep": {"duration_min": 438},
        "analysis": {"recovery_focus": False},
        "errors": [],
    }


def _evening_payload(marker: str = "first") -> dict:
    return {
        "date": "2026-11-27",
        "status": "success",
        "generated_at": "2026-11-27T22:00:00+08:00",
        "activity_count": 1,
        "totals": {"distance_km": 5.0, "duration_min": 30, "training_load": 50.0},
        "activities": [{"id": 1, "name": "Morning Run", "marker": marker}],
        "training_status_current": {"training_status": "Productive"},
        "errors": [],
    }


class TestLedgerStore:
    def test_write_creates_private_json_and_markdown(self, tmp_path: Path) -> None:
        root = tmp_path / "ledger"
        store = LedgerStore(root)

        json_path, markdown_path = store.write("2026-11-27", "morning", _morning_payload())

        document = json.loads(json_path.read_text(encoding="utf-8"))
        assert document["morning"]["hrv"]["marker"] == "first"
        assert "晨间记录" in markdown_path.read_text(encoding="utf-8")
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE(json_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(markdown_path.stat().st_mode) == 0o600

    def test_same_slot_rerun_replaces_without_duplicate_section(self, tmp_path: Path) -> None:
        store = LedgerStore(tmp_path)
        store.write("2026-11-27", "morning", _morning_payload("first"))

        json_path, markdown_path = store.write("2026-11-27", "morning", _morning_payload("second"))

        document = json.loads(json_path.read_text(encoding="utf-8"))
        assert document["morning"]["hrv"]["marker"] == "second"
        assert markdown_path.read_text(encoding="utf-8").count("晨间记录") == 1

    def test_failed_rerun_does_not_replace_success(self, tmp_path: Path) -> None:
        store = LedgerStore(tmp_path)
        _, markdown_path = store.write("2026-11-27", "morning", _morning_payload("first"))
        failed = _morning_payload("failed")
        failed["status"] = "partial"
        failed["errors"] = ["HRV data unavailable"]
        markdown_path.unlink()

        json_path, markdown_path = store.write("2026-11-27", "morning", failed)

        document = json.loads(json_path.read_text(encoding="utf-8"))
        assert document["morning"]["hrv"]["marker"] == "first"
        assert document["morning"]["status"] == "success"
        assert "HRV data unavailable" not in markdown_path.read_text(encoding="utf-8")
        assert "晨间记录" in markdown_path.read_text(encoding="utf-8")

    def test_morning_and_evening_merge_into_same_day(self, tmp_path: Path) -> None:
        store = LedgerStore(tmp_path)
        store.write("2026-11-27", "morning", _morning_payload())

        json_path, markdown_path = store.write("2026-11-27", "evening", _evening_payload())

        document = json.loads(json_path.read_text(encoding="utf-8"))
        assert set(document) == {"date", "morning", "evening", "updated_at"}
        markdown = markdown_path.read_text(encoding="utf-8")
        assert "晨间记录" in markdown
        assert "晚间复盘" in markdown

    def test_markdown_is_rebuilt_from_json_when_missing(self, tmp_path: Path) -> None:
        store = LedgerStore(tmp_path)
        json_path, markdown_path = store.write("2026-11-27", "morning", _morning_payload())
        markdown_path.unlink()

        _, rebuilt_path = store.write("2026-11-27", "evening", _evening_payload())

        document = json.loads(json_path.read_text(encoding="utf-8"))
        assert rebuilt_path.read_text(encoding="utf-8") == render_markdown(document)
        assert "晨间记录" in rebuilt_path.read_text(encoding="utf-8")
        assert "晚间复盘" in rebuilt_path.read_text(encoding="utf-8")

    def test_failed_rerun_repairs_stale_markdown_from_canonical_json(self, tmp_path: Path, monkeypatch) -> None:
        store = LedgerStore(tmp_path)
        json_path, markdown_path = store.write("2026-11-27", "morning", _morning_payload("first"))
        original_atomic_write = ledger_module._atomic_write
        second = _morning_payload("second")
        second["sleep"]["duration_min"] = 400

        def fail_markdown(path: Path, content: str) -> None:
            if path.suffix == ".md":
                raise OSError("markdown down")
            original_atomic_write(path, content)

        with monkeypatch.context() as patch:
            patch.setattr(ledger_module, "_atomic_write", fail_markdown)
            with pytest.raises(OSError, match="markdown down"):
                store.write("2026-11-27", "morning", second)

        assert json.loads(json_path.read_text(encoding="utf-8"))["morning"]["hrv"]["marker"] == "second"
        assert "438" in markdown_path.read_text(encoding="utf-8")

        failed = _morning_payload("failed")
        failed["status"] = "partial"
        store.write("2026-11-27", "morning", failed)

        document = json.loads(json_path.read_text(encoding="utf-8"))
        assert document["morning"]["hrv"]["marker"] == "second"
        assert "400" in markdown_path.read_text(encoding="utf-8")
        assert markdown_path.read_text(encoding="utf-8") == render_markdown(document)

    def test_atomic_write_leaves_previous_file_on_failure(self, tmp_path: Path, monkeypatch) -> None:
        store = LedgerStore(tmp_path)
        json_path, _ = store.write("2026-11-27", "morning", _morning_payload("first"))
        previous = json_path.read_text(encoding="utf-8")

        def fail_replace(source, destination):
            raise OSError("replace failed")

        monkeypatch.setattr("garmin_mcp_lite.tools.ledger.os.replace", fail_replace)
        with pytest.raises(OSError, match="replace failed"):
            store.write("2026-11-27", "morning", _morning_payload("second"))

        assert json_path.read_text(encoding="utf-8") == previous
        assert not list(tmp_path.glob("*.tmp-*"))

    def test_concurrent_writes_preserve_both_slots(self, tmp_path: Path) -> None:
        store = LedgerStore(tmp_path)

        with ThreadPoolExecutor(max_workers=2) as pool:
            morning = pool.submit(store.write, "2026-11-27", "morning", _morning_payload())
            evening = pool.submit(store.write, "2026-11-27", "evening", _evening_payload())
            morning.result()
            evening.result()

        document = json.loads((tmp_path / "2026-11-27.json").read_text(encoding="utf-8"))
        assert document["morning"]["hrv"]["status"] == "BALANCED"
        assert document["evening"]["activity_count"] == 1

    def test_default_root_uses_environment_override(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("GARMIN_LEDGER_DIR", str(tmp_path / "custom"))

        store = LedgerStore()

        assert store.root == tmp_path / "custom"


class TestLedgerLogging:
    @pytest.mark.parametrize(
        ("message", "secret"),
        [
            ("Authorization: Basic basic-secret", "basic-secret"),
            ("Cookie: session=cookie-secret; theme=dark", "cookie-secret"),
            ("Set-Cookie: session=set-cookie-secret", "set-cookie-secret"),
            ("api_key=key-secret", "key-secret"),
        ],
    )
    def test_redacts_complete_credential_headers_and_api_keys(self, message: str, secret: str) -> None:
        assert secret not in _redact_text(message)

    def test_safe_error_discards_raw_json_payload_content(self) -> None:
        result = _safe_error(RuntimeError('{"access_token":"json-secret","activities":[{"name":"private-run"}]}'))

        assert "json-secret" not in result
        assert "private-run" not in result
        assert "<redacted>" in result

    def test_safe_error_uses_exception_type_for_empty_message(self) -> None:
        assert _safe_error(RuntimeError("")) == "RuntimeError"

    def test_log_sanitizes_token_like_error_text(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        logger = configure_logging(log_dir)

        logger.error("request failed token=super-secret password=hidden")
        for handler in logger.handlers:
            handler.flush()

        log_path = log_dir / "ledger.log"
        content = log_path.read_text(encoding="utf-8")
        assert "super-secret" not in content
        assert "hidden" not in content
        assert "<redacted>" in content
        assert stat.S_IMODE(log_path.stat().st_mode) == 0o600

    def test_log_sanitizes_headers_json_and_bearer_tokens(self, tmp_path: Path) -> None:
        logger = configure_logging(tmp_path)
        logger.error(
            'Authorization: Bearer header-secret {"token": "json-secret"} '
            "access_token=query-secret bearer bare-secret"
        )
        for handler in logger.handlers:
            handler.flush()

        content = (tmp_path / "ledger.log").read_text(encoding="utf-8")
        for secret in ("header-secret", "json-secret", "query-secret", "bare-secret"):
            assert secret not in content
        assert content.count("<redacted>") >= 4


class TestLedgerCli:
    def test_cli_morning_writes_today_by_default(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(ledger_module, "today_str", lambda: "2026-11-27")
        monkeypatch.setattr(ledger_module, "run_ledger", lambda mode, date: _morning_payload())
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logging.getLogger("test-ledger"))

        exit_code = main(["morning", "--ledger-dir", str(tmp_path)])

        assert exit_code == 0
        assert (tmp_path / "2026-11-27.json").exists()
        assert (tmp_path / "2026-11-27.md").exists()

    def test_cli_evening_accepts_explicit_date(self, tmp_path: Path, monkeypatch) -> None:
        calls = []

        def fake_run(mode, date):
            calls.append((mode, date))
            return _evening_payload()

        monkeypatch.setattr(ledger_module, "run_ledger", fake_run)
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logging.getLogger("test-ledger"))

        exit_code = main(["evening", "--date", "2026-11-26", "--ledger-dir", str(tmp_path)])

        assert exit_code == 0
        assert calls == [("evening", "2026-11-26")]
        assert (tmp_path / "2026-11-26.json").exists()

    def test_cli_success_returns_zero(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(ledger_module, "run_ledger", lambda mode, date: _morning_payload())
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logging.getLogger("test-ledger"))

        assert main(["morning", "--date", "2026-11-27", "--ledger-dir", str(tmp_path)]) == 0

    def test_cli_partial_returns_nonzero_but_writes_ledger(self, tmp_path: Path, monkeypatch) -> None:
        payload = _morning_payload()
        payload["status"] = "partial"
        monkeypatch.setattr(ledger_module, "run_ledger", lambda mode, date: payload)
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logging.getLogger("test-ledger"))

        assert main(["morning", "--date", "2026-11-27", "--ledger-dir", str(tmp_path)]) == 1
        assert (tmp_path / "2026-11-27.json").exists()

    def test_cli_invalid_date_returns_two(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logging.getLogger("test-ledger"))

        assert main(["morning", "--date", "not-a-date", "--ledger-dir", str(tmp_path)]) == 2

    def test_cli_ledger_dir_override(self, tmp_path: Path, monkeypatch) -> None:
        target = tmp_path / "custom-ledger"
        monkeypatch.setattr(ledger_module, "run_ledger", lambda mode, date: _morning_payload())
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logging.getLogger("test-ledger"))

        assert main(["morning", "--date", "2026-11-27", "--ledger-dir", str(target)]) == 0
        assert (target / "2026-11-27.json").exists()

    def test_cli_exception_returns_one(self, tmp_path: Path, monkeypatch) -> None:
        def fail_run(mode, date):
            raise RuntimeError("token=super-secret")

        logger = logging.getLogger("test-ledger-error")
        monkeypatch.setattr(ledger_module, "run_ledger", fail_run)
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logger)

        assert main(["morning", "--date", "2026-11-27", "--ledger-dir", str(tmp_path)]) == 1
        document = json.loads((tmp_path / "2026-11-27.json").read_text(encoding="utf-8"))
        assert document["morning"]["status"] == "unavailable"
        assert "super-secret" not in str(document)

    def test_cli_without_mode_returns_two(self, monkeypatch) -> None:
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logging.getLogger("test-ledger"))

        assert main([]) == 2

    def test_cli_logging_setup_failure_returns_one(self, monkeypatch) -> None:
        def fail_logging(log_dir=None):
            raise RuntimeError("log down")

        monkeypatch.setattr(ledger_module, "configure_logging", fail_logging)

        assert main(["morning", "--date", "2026-11-27"]) == 1

    def test_cli_store_failure_returns_one(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(ledger_module, "configure_logging", lambda log_dir=None: logging.getLogger("test-ledger"))
        monkeypatch.setattr(ledger_module, "run_ledger", lambda mode, date: _morning_payload())

        def fail_write(self, date, mode, payload):
            raise OSError("disk full")

        monkeypatch.setattr(ledger_module.LedgerStore, "write", fail_write)

        assert main(["morning", "--date", "2026-11-27", "--ledger-dir", str(tmp_path)]) == 1


class TestLedgerEdgeCases:
    def test_morning_includes_sleep_quality_signal(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {"calendarDate": "2026-11-27", "status": "BALANCED"}
        }
        sleep = _sleep_payload()
        sleep["dailySleepDTO"]["sleepScores"] = {"overall": {"value": 82, "qualifierKey": "FAIR"}}
        mock_get_client.get_sleep_data.return_value = sleep

        result = collect_morning("2026-11-27")

        assert "Sleep quality: FAIR" in result["analysis"]["signals"]

    def test_morning_without_status_signals_is_explicit(self, monkeypatch) -> None:
        monkeypatch.setattr(ledger_module.hrv, "get_hrv_status", lambda date: {"status": ""})
        monkeypatch.setattr(
            ledger_module.health,
            "get_health_data",
            lambda metric, date: {"sleep": {"score": 80, "duration_min": 420}},
        )

        result = collect_morning("2026-11-27")

        assert result["analysis"]["signals"] == ["Insufficient data for recovery analysis"]

    def test_morning_empty_sleep_payload_is_unavailable(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {"hrvSummary": {}}
        mock_get_client.get_sleep_data.return_value = {"dailySleepDTO": {}}

        result = collect_morning("2026-11-27")

        assert result["status"] == "unavailable"
        assert result["sleep"]["error"] == "Sleep data unavailable"

    def test_morning_non_dict_sleep_payload_is_unavailable(self, mock_get_client: MagicMock, monkeypatch) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {"calendarDate": "2026-11-27", "status": "BALANCED"}
        }
        monkeypatch.setattr(ledger_module.health, "get_health_data", lambda metric, date: {"sleep": None})

        result = collect_morning("2026-11-27")

        assert result["status"] == "partial"
        assert result["sleep"]["error"] == "Sleep data unavailable"

    def test_morning_missing_core_data_has_no_normal_day_conclusion(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {"hrvSummary": {}}
        mock_get_client.get_sleep_data.return_value = {"dailySleepDTO": {}}

        result = collect_morning("2026-11-27")

        assert result["status"] == "unavailable"
        assert result["analysis"]["recovery_focus"] is None
        assert result["analysis"]["summary"] == "Insufficient data for recovery analysis"

    def test_partial_morning_with_only_hrv_does_not_infer_normal_day(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {"calendarDate": "2026-11-27", "status": "BALANCED"}
        }
        mock_get_client.get_sleep_data.side_effect = RuntimeError("sleep down")

        result = collect_morning("2026-11-27")

        assert result["status"] == "partial"
        assert result["analysis"]["recovery_focus"] is None
        assert result["analysis"]["summary"] == "Insufficient data for recovery analysis"

    def test_partial_morning_with_only_sleep_does_not_infer_normal_day(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {"hrvSummary": {}}
        mock_get_client.get_sleep_data.return_value = _sleep_payload()

        result = collect_morning("2026-11-27")

        assert result["status"] == "partial"
        assert result["analysis"]["recovery_focus"] is None
        assert result["analysis"]["summary"] == "Insufficient data for recovery analysis"

    def test_partial_morning_retains_explicit_recovery_signal(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {"calendarDate": "2026-11-27", "status": "UNBALANCED"}
        }
        mock_get_client.get_sleep_data.side_effect = RuntimeError("sleep down")

        result = collect_morning("2026-11-27")

        assert result["status"] == "partial"
        assert result["analysis"]["recovery_focus"] is True
        assert "partial data" in result["analysis"]["summary"].lower()

    def test_low_sleep_score_without_qualifier_has_insufficient_analysis(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_hrv_data.return_value = {
            "hrvSummary": {"calendarDate": "2026-11-27", "status": "BALANCED"}
        }
        sleep = _sleep_payload()
        sleep["dailySleepDTO"]["sleepScore"] = 45
        sleep["dailySleepDTO"].pop("sleepScores")
        mock_get_client.get_sleep_data.return_value = sleep

        result = collect_morning("2026-11-27")

        assert result["status"] == "success"
        assert result["analysis"]["recovery_focus"] is None
        assert result["analysis"]["summary"] == "Insufficient data for recovery analysis"

    def test_morning_helper_exceptions_are_captured_and_sanitized(self, monkeypatch) -> None:
        def fail_hrv(date):
            raise RuntimeError("token=hrv-secret")

        def fail_sleep(metric, date):
            raise RuntimeError('{"password": "sleep-secret"}')

        monkeypatch.setattr(ledger_module.hrv, "get_hrv_status", fail_hrv)
        monkeypatch.setattr(ledger_module.health, "get_health_data", fail_sleep)

        result = collect_morning("2026-11-27")

        assert result["status"] == "unavailable"
        assert "hrv-secret" not in str(result)
        assert "sleep-secret" not in str(result)
        assert result["errors"]

    def test_morning_persisted_error_fields_are_sanitized(self, monkeypatch) -> None:
        monkeypatch.setattr(
            ledger_module.hrv,
            "get_hrv_status",
            lambda date: {"status": "NO_DATA", "error": "access_token=hrv-secret"},
        )
        monkeypatch.setattr(
            ledger_module.health,
            "get_health_data",
            lambda metric, date: {"sleep": {"error": '{"token": "sleep-secret"}'}},
        )

        result = collect_morning("2026-11-27")

        assert "hrv-secret" not in str(result)
        assert "sleep-secret" not in str(result)
        assert result["hrv"]["error"] == "access_token=<redacted>"
        assert result["sleep"]["error"] == "<redacted>"

    def test_evening_skips_non_dict_activity_rows(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities_by_date.return_value = [None, _activity(1, "Morning Run", 5000, 1800)]
        mock_get_client.get_activity.return_value = _activity_detail(1, 50.0)

        result = collect_evening("2026-11-27")

        assert result["activity_count"] == 1

    def test_evening_missing_training_load_is_unknown(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_activities_by_date.return_value = [_activity(1, "Morning Run", 5000, 1800)]
        mock_get_client.get_activity.return_value = _activity_detail(1, 50.0)
        mock_get_client.get_activity.return_value["summaryDTO"].pop("activityTrainingLoad")

        result = collect_evening("2026-11-27")

        assert result["totals"]["training_load"] is None
        assert result["totals"]["training_load_complete"] is False

    def test_evening_training_status_failure_is_partial(self, mock_get_client: MagicMock, monkeypatch) -> None:
        mock_get_client.get_activities_by_date.return_value = []

        def fail_status():
            raise RuntimeError("status down")

        monkeypatch.setattr(ledger_module.training, "get_training_status", fail_status)

        result = collect_evening("2026-11-27")

        assert result["status"] == "partial"
        assert result["training_status_current"]["error"] == "status down"
        assert result["errors"] == ["status down"]

    def test_run_ledger_dispatches_both_modes(self, monkeypatch) -> None:
        monkeypatch.setattr(ledger_module, "collect_morning", lambda date: {"mode": "morning", "date": date})
        monkeypatch.setattr(ledger_module, "collect_evening", lambda date: {"mode": "evening", "date": date})

        assert run_ledger("morning", "2026-11-27") == {"mode": "morning", "date": "2026-11-27"}
        assert run_ledger("evening", "2026-11-26") == {"mode": "evening", "date": "2026-11-26"}

    def test_render_markdown_handles_empty_document_and_bad_rows(self) -> None:
        assert "暂无记录" in render_markdown({"date": "2026-11-27"})

        evening = _evening_payload()
        evening["activities"] = [None, {"name": "Broken detail", "detail_error": "detail down"}]
        markdown = render_markdown({"date": "2026-11-27", "evening": evening})

        assert "详情错误：detail down" in markdown

    def test_render_markdown_labels_historical_training_status_as_runtime_current(self) -> None:
        markdown = render_markdown({"date": "2026-11-27", "evening": _evening_payload()})

        assert "运行时当前训练状态" in markdown
        assert "状态采集时间" in markdown

    def test_render_markdown_includes_required_analysis_fields(self) -> None:
        morning = _morning_payload()
        morning["hrv"].update(
            {
                "baseline": {"balanced_low": 45, "balanced_upper": 65},
                "training_guidance": "Keep intensity easy",
            }
        )
        morning["sleep"].update({"light_min": 302, "awake_min": 21, "score_quality": "FAIR"})
        morning["errors"] = ["HRV data unavailable"]

        evening = _evening_payload()
        evening["training_status_current"]["acute_load_detail"] = {"ratio": 0.9, "status": "OPTIMAL"}
        evening["training_status_current"]["four_week_load"] = {
            "aerobic_low": {"load": 1252, "target_min": 433, "target_max": 952},
            "anaerobic": {"load": 120, "target_min": 173, "target_max": 519},
        }
        evening["training_status_current"]["readiness"] = {"score": 62, "level": "MODERATE"}
        evening["errors"] = ["activity 1: detail down"]

        markdown = render_markdown({"date": "2026-11-27", "morning": morning, "evening": evening})

        for expected in (
            "HRV 基线：45 - 65 ms",
            "浅睡：302 分钟",
            "清醒：21 分钟",
            "Keep intensity easy",
            "ACWR：0.9（OPTIMAL）",
            "四周负荷目标",
            "准备度：62",
            "HRV data unavailable",
            "activity 1: detail down",
        ):
            assert expected in markdown

    def test_configure_logging_replaces_previous_handlers(self, tmp_path: Path) -> None:
        first = configure_logging(tmp_path)
        second = configure_logging(tmp_path)

        assert first is second
        assert len(second.handlers) == 1


class TestReadLedger:
    def test_missing_date_returns_found_false(self, tmp_path: Path) -> None:
        result = read_ledger("2026-11-27", tmp_path)
        assert result["found"] is False
        assert result["date"] == "2026-11-27"
        assert result["json_path"].endswith("2026-11-27.json")

    def test_reads_existing_document_without_writing(self, tmp_path: Path) -> None:
        store = LedgerStore(tmp_path)
        store.write("2026-11-27", "morning", {"date": "2026-11-27", "status": "success"})
        before = sorted(path.name for path in tmp_path.iterdir())

        result = read_ledger("2026-11-27", tmp_path)

        assert result["found"] is True
        assert result["document"]["morning"]["status"] == "success"
        assert sorted(path.name for path in tmp_path.iterdir()) == before

    def test_invalid_date_returns_error(self, tmp_path: Path) -> None:
        result = read_ledger("2026-1-1", tmp_path)
        assert result["found"] is False
        assert "YYYY-MM-DD" in result["error"]
