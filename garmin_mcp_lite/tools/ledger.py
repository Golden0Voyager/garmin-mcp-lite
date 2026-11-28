from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import re
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Literal, cast

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools import activities, health, hrv, training
from garmin_mcp_lite.tools._common import as_dict, as_list, summarize_activity, today_str

_LedgerMode = Literal["morning", "evening"]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _redact_text(message: str) -> str:
    message = re.sub(
        r"(?i)(?P<prefix>[\"']?authorization[\"']?\s*[:=]\s*)(?:(?:bearer|basic)\s+)?[^\s,;\"'}]+",
        r"\g<prefix><redacted>",
        message,
    )
    message = re.sub(
        r"(?i)(?P<prefix>[\"']?(?:set-)?cookie[\"']?\s*[:=]\s*)[^\r\n\"'}]+",
        r"\g<prefix><redacted>",
        message,
    )
    message = re.sub(r"(?i)\b(bearer)\s+[^\s,;]+", r"\1 <redacted>", message)
    return re.sub(
        r"(?i)(?P<prefix>[\"']?[A-Za-z0-9_]*(?:token|password|passwd|secret|ssecurity|credential|api[_-]?key|apikey|session[_-]?id|cookie)[A-Za-z0-9_]*[\"']?\s*[:=]\s*)(?P<quote>[\"']?)[^\s,;\"']+",
        lambda match: f"{match.group('prefix')}{match.group('quote')}<redacted>",
        message,
    )


def _safe_error_text(message: str) -> str:
    """Redact credentials and discard unstructured payload-like error bodies."""
    redacted = _redact_text(message).strip()
    if not redacted:
        return ""
    if any(marker in redacted for marker in ("{", "}", "[", "]", "\n", "\r")) or re.search(
        r"(?i)<!doctype|<html", redacted
    ):
        return "<redacted>"
    return redacted[:500]


def _sanitize_error_fields(data: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(data)
    if isinstance(sanitized.get("error"), str):
        sanitized["error"] = _safe_error_text(sanitized["error"])
    return sanitized


def _safe_error(error: Exception) -> str:
    """Return a bounded error string with credentials and raw payloads removed."""
    return _safe_error_text(str(error)) or type(error).__name__


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _redact_text(super().format(record))


class _PrivateRotatingFileHandler(RotatingFileHandler):
    """Rotating handler whose files are always owner-only."""

    def _open(self):  # type: ignore[no-untyped-def]
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.chmod(self.baseFilename, 0o600)
        return os.fdopen(fd, self.mode, encoding=self.encoding, errors=self.errors)


def configure_logging(log_dir: Path | None = None) -> logging.Logger:
    """Configure the ledger logger with private, rotating, redacted output."""
    root = log_dir or Path(os.environ.get("GARMIN_LOG_DIR", Path.home() / ".garmin-mcp-lite" / "logs"))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)

    logger = logging.getLogger("garmin_mcp_lite.ledger")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = _PrivateRotatingFileHandler(
        root / "ledger.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def _default_ledger_root() -> Path:
    return Path(os.environ.get("GARMIN_LEDGER_DIR", Path.home() / ".garmin-mcp-lite" / "ledger"))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    except Exception:
        with suppress(FileNotFoundError):
            temporary_path.unlink()
        raise


@contextmanager
def _date_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _render_morning(payload: dict[str, Any]) -> list[str]:
    hrv_data = as_dict(payload.get("hrv"))
    sleep_data = as_dict(payload.get("sleep"))
    analysis = as_dict(payload.get("analysis"))
    baseline = as_dict(hrv_data.get("baseline"))
    lines = [
        "## 晨间记录",
        "",
        f"- 状态：{_display(payload.get('status'))}",
        f"- HRV 状态：{_display(hrv_data.get('status'))}",
        f"- 昨晚 HRV：{_display(hrv_data.get('last_night_avg_ms'))} ms",
        f"- 周平均 HRV：{_display(hrv_data.get('weekly_avg_ms'))} ms",
        f"- HRV 基线：{_display(baseline.get('balanced_low'))} - {_display(baseline.get('balanced_upper'))} ms",
        f"- HRV 建议：{_display(hrv_data.get('training_guidance'))}",
        f"- 睡眠评分：{_display(sleep_data.get('score'))}",
        f"- 睡眠质量：{_display(sleep_data.get('score_quality'))}",
        f"- 睡眠时长：{_display(sleep_data.get('duration_min'))} 分钟",
        f"- 深睡：{_display(sleep_data.get('deep_min'))} 分钟",
        f"- 浅睡：{_display(sleep_data.get('light_min'))} 分钟",
        f"- REM：{_display(sleep_data.get('rem_min'))} 分钟",
        f"- 清醒：{_display(sleep_data.get('awake_min'))} 分钟",
        f"- 静息心率：{_display(sleep_data.get('resting_hr'))} bpm",
        f"- 恢复优先：{_display(analysis.get('recovery_focus'))}",
        f"- 结论：{_display(analysis.get('summary'))}",
        "",
    ]
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        lines.extend(["### 错误", "", *[f"- {_display(error)}" for error in errors], ""])
    return lines


def _render_evening(payload: dict[str, Any]) -> list[str]:
    totals = as_dict(payload.get("totals"))
    current = as_dict(payload.get("training_status_current"))
    acute = as_dict(current.get("acute_load_detail"))
    four_week = as_dict(current.get("four_week_load"))
    aerobic = as_dict(four_week.get("aerobic_low"))
    anaerobic = as_dict(four_week.get("anaerobic"))
    readiness = as_dict(current.get("readiness"))
    lines = [
        "## 晚间复盘",
        "",
        f"- 状态：{_display(payload.get('status'))}",
        f"- 活动数量：{_display(payload.get('activity_count'))}",
        f"- 总距离：{_display(totals.get('distance_km'))} km",
        f"- 总时长：{_display(totals.get('duration_min'))} 分钟",
        f"- 总训练负荷：{_display(totals.get('training_load'))}",
        f"- 训练负荷完整：{_display(totals.get('training_load_complete'))}",
        f"- 运行时当前训练状态：{_display(current.get('training_status'))}",
        f"- 当前急性负荷：{_display(current.get('acute_load'))}",
        f"- ACWR：{_display(acute.get('ratio'))}（{_display(acute.get('status'))}）",
        f"- 四周负荷目标：有氧低 {_display(aerobic.get('load'))}（{_display(aerobic.get('target_min'))}–{_display(aerobic.get('target_max'))}），无氧 {_display(anaerobic.get('load'))}（{_display(anaerobic.get('target_min'))}–{_display(anaerobic.get('target_max'))}）",
        f"- 准备度：{_display(readiness.get('score'))}（{_display(readiness.get('level'))}）",
        f"- 状态采集时间：{_display(current.get('as_of'))}",
        "",
    ]
    rows = as_list(payload.get("activities"))
    for row in rows:
        if not isinstance(row, dict):
            continue
        effect = as_dict(row.get("training_effect"))
        lines.extend(
            [
                f"### {_display(row.get('name'))}",
                "",
                f"- 类型：{_display(row.get('type'))}",
                f"- 距离：{_display(row.get('distance_km'))} km",
                f"- 时长：{_display(row.get('duration_min'))} 分钟",
                f"- 平均心率：{_display(row.get('avg_hr'))} bpm",
                f"- 配速：{_display(row.get('pace'))}",
                f"- 训练负荷：{_display(row.get('training_load'))}",
                f"- 有氧训练效果：{_display(effect.get('aerobic'))}",
                f"- 无氧训练效果：{_display(effect.get('anaerobic'))}",
                "",
            ]
        )
        if row.get("detail_error"):
            lines.extend([f"- 详情错误：{_display(row.get('detail_error'))}", ""])
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        lines.extend(["### 错误", "", *[f"- {_display(error)}" for error in errors], ""])
    return lines


def render_markdown(document: dict[str, Any]) -> str:
    """Render a canonical ledger JSON document as Markdown."""
    lines = [f"# Garmin 每日台账 — {_display(document.get('date'))}", ""]
    morning = document.get("morning")
    evening = document.get("evening")
    if isinstance(morning, dict):
        lines.extend(_render_morning(morning))
    if isinstance(evening, dict):
        lines.extend(_render_evening(evening))
    if not isinstance(morning, dict) and not isinstance(evening, dict):
        lines.extend(["暂无记录", ""])
    return "\n".join(lines).rstrip() + "\n"


class LedgerStore:
    """Private, atomic JSON/Markdown ledger storage."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _default_ledger_root()

    def write(
        self,
        date: str,
        mode: _LedgerMode,
        payload: dict[str, Any],
    ) -> tuple[Path, Path]:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        json_path = self.root / f"{date}.json"
        markdown_path = self.root / f"{date}.md"
        lock_path = self.root / f"{date}.lock"

        with _date_lock(lock_path):
            document = (
                json.loads(json_path.read_text(encoding="utf-8"))
                if json_path.exists()
                else {"date": date}
            )
            existing = document.get(mode)
            if (
                isinstance(existing, dict)
                and existing.get("status") == "success"
                and payload.get("status") != "success"
            ):
                markdown = render_markdown(document)
                if not markdown_path.exists() or markdown_path.read_text(encoding="utf-8") != markdown:
                    _atomic_write(markdown_path, markdown)
                return json_path, markdown_path
            document[mode] = payload
            document["updated_at"] = _now_iso()
            _atomic_write(json_path, json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            _atomic_write(markdown_path, render_markdown(document))

        return json_path, markdown_path


def read_ledger(date: str, ledger_dir: Path | None = None) -> dict[str, Any]:
    """Read a daily ledger JSON document without writing or modifying files.

    Args:
        date: Ledger date in YYYY-MM-DD format.
        ledger_dir: Optional ledger directory override; defaults to the
            configured GARMIN_LEDGER_DIR or ~/.garmin-mcp-lite/ledger.
    """
    try:
        _parse_date(date)
    except argparse.ArgumentTypeError as exc:
        return {"date": date, "found": False, "error": str(exc)}

    root = Path(ledger_dir) if ledger_dir is not None else _default_ledger_root()
    json_path = root / f"{date}.json"
    markdown_path = root / f"{date}.md"
    if not json_path.exists():
        return {
            "date": date,
            "found": False,
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
        }

    document = json.loads(json_path.read_text(encoding="utf-8"))
    return {
        "date": date,
        "found": True,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "document": document,
    }


def _parse_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record Garmin morning and evening training ledgers.")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("morning", "evening"):
        command = subparsers.add_parser(mode, help=f"Record the {mode} ledger")
        command.add_argument("--date", type=_parse_date, help="Garmin date in YYYY-MM-DD format")
        command.add_argument("--ledger-dir", type=Path, help="Override the ledger directory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ledger CLI and return a process exit code."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    date = args.date or today_str()
    mode = cast(_LedgerMode, args.mode)
    logger = logging.getLogger("garmin_mcp_lite.ledger")
    try:
        configure_logging()
    except Exception as exc:
        logger.error("logging setup failed: %s", _safe_error(exc))
        return 1

    try:
        payload = run_ledger(mode, date)
    except Exception as exc:
        payload = {
            "date": date,
            "status": "unavailable",
            "generated_at": _now_iso(),
            "errors": [_safe_error(exc)],
        }

    try:
        store = LedgerStore(args.ledger_dir)
        json_path, markdown_path = store.write(date, mode, payload)
    except Exception as exc:
        logger.error("ledger %s failed for %s: %s", mode, date, _safe_error(exc))
        return 1

    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if payload.get("status") == "success" else 1


def _morning_analysis(
    hrv_data: dict[str, Any],
    sleep_data: dict[str, Any],
    *,
    complete: bool,
) -> dict[str, Any]:
    hrv_status = str(hrv_data.get("status") or "").upper()
    sleep_quality = str(sleep_data.get("score_quality") or "").upper()
    recovery_signal = hrv_status in {"UNBALANCED", "LOW", "POOR"} or sleep_quality in {"FAIR", "POOR"}

    signals: list[str] = []
    if hrv_status:
        signals.append(f"HRV: {hrv_status}")
    if sleep_quality:
        signals.append(f"Sleep quality: {sleep_quality}")
    if not signals:
        signals.append("Insufficient data for recovery analysis")

    if recovery_signal:
        return {
            "recovery_focus": True,
            "summary": "Recovery-first day" if complete else "Recovery-first day (partial data)",
            "signals": signals,
        }
    if complete and hrv_status == "BALANCED" and sleep_quality in {"GOOD", "EXCELLENT"}:
        return {
            "recovery_focus": False,
            "summary": "Normal training day",
            "signals": signals,
        }
    return {
        "recovery_focus": None,
        "summary": "Insufficient data for recovery analysis",
        "signals": signals,
    }


def collect_morning(date: str) -> dict[str, Any]:
    """Collect HRV and sleep data for one Garmin wake date."""
    errors: list[str] = []

    try:
        hrv_data = _sanitize_error_fields(hrv.get_hrv_status(date))
    except Exception as exc:
        hrv_data = {"error": _safe_error(exc)}
    hrv_ok = "error" not in hrv_data and hrv_data.get("status") not in {"NO_DATA", "NONE"}
    if not hrv_ok:
        errors.append(str(hrv_data.get("error") or "HRV data unavailable"))

    try:
        sleep_response = health.get_health_data("sleep", date)
    except Exception as exc:
        sleep_response = {"sleep": {"error": _safe_error(exc)}}
    sleep_data = sleep_response.get("sleep")
    if not isinstance(sleep_data, dict):
        sleep_data = {}
    sleep_data = _sanitize_error_fields(sleep_data)
    sleep_ok = "error" not in sleep_data
    if not sleep_ok:
        errors.append(str(sleep_data.get("error") or "Sleep data unavailable"))
    elif sleep_data.get("score") is None and sleep_data.get("duration_min") is None:
        sleep_data = {**sleep_data, "error": "Sleep data unavailable"}
        sleep_ok = False
        errors.append("Sleep data unavailable")

    if hrv_ok and sleep_ok:
        status = "success"
    elif hrv_ok or sleep_ok:
        status = "partial"
    else:
        status = "unavailable"

    analysis = _morning_analysis(hrv_data, sleep_data, complete=status == "success")

    return {
        "date": date,
        "status": status,
        "generated_at": _now_iso(),
        "hrv": hrv_data,
        "sleep": sleep_data,
        "analysis": analysis,
        "errors": errors,
    }


def collect_evening(date: str) -> dict[str, Any]:
    """Collect all activities for one date plus the current training status."""
    errors: list[str] = []
    client = get_client()

    try:
        raw_activities = as_list(client.get_activities_by_date(date, date))
    except Exception as exc:
        message = _safe_error(exc)
        return {
            "date": date,
            "status": "unavailable",
            "generated_at": _now_iso(),
            "activity_count": 0,
            "totals": {
                "distance_km": 0.0,
                "duration_min": 0,
                "training_load": 0.0,
                "training_load_complete": True,
            },
            "activities": [],
            "training_status_current": {"as_of": _now_iso()},
            "errors": [message],
        }

    activity_rows: list[dict[str, Any]] = []
    total_distance = 0.0
    total_duration = 0
    load_values: list[float] = []
    load_complete = True

    for raw_activity in raw_activities:
        if not isinstance(raw_activity, dict):
            continue
        summary = summarize_activity(raw_activity)
        activity_id = summary.get("id")
        if activity_id is not None:
            try:
                detail = activities.get_activity_detail(int(activity_id))
                summary["training_load"] = detail.get("training_load")
                summary["training_effect"] = detail.get("training_effect")
                load = detail.get("training_load")
                if isinstance(load, (int, float)):
                    load_values.append(float(load))
                else:
                    load_complete = False
            except Exception as exc:
                message = _safe_error(exc)
                summary["detail_error"] = message
                errors.append(f"activity {activity_id}: {message}")
                load_complete = False

        distance = summary.get("distance_km")
        duration = summary.get("duration_min")
        if isinstance(distance, (int, float)):
            total_distance += float(distance)
        if isinstance(duration, (int, float)):
            total_duration += int(duration)
        activity_rows.append(summary)

    try:
        training_status = training.get_training_status()
    except Exception as exc:
        message = _safe_error(exc)
        training_status = {"error": message}
        errors.append(message)

    return {
        "date": date,
        "status": "partial" if errors else "success",
        "generated_at": _now_iso(),
        "activity_count": len(activity_rows),
        "totals": {
            "distance_km": round(total_distance, 2),
            "duration_min": total_duration,
            "training_load": round(sum(load_values), 1) if load_values else (0.0 if not activity_rows else None),
            "training_load_complete": load_complete if activity_rows else True,
        },
        "activities": activity_rows,
        "training_status_current": {"as_of": _now_iso(), **training_status},
        "errors": errors,
    }


def run_ledger(mode: _LedgerMode, date: str) -> dict[str, Any]:
    """Run one ledger collection mode."""
    if mode == "morning":
        return collect_morning(date)
    if mode == "evening":
        return collect_evening(date)
    raise ValueError(f"Unsupported ledger mode: {mode}")
