# Garmin 每日台账自动化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加一个确定性本地 CLI，按起床日期记录 HRV/睡眠晨间台账，按活动日期记录训练复盘，并由 Qoder Desktop 在每天 10:00 和 22:00（Asia/Shanghai）自动调用。

**Architecture:** 新增 `garmin_mcp_lite.ledger` 模块，分为数据收集、分析、持久化与 CLI 四层；复用现有 Garmin 工具函数。JSON 是 canonical 数据，Markdown 由 JSON 渲染，同日期写入通过文件锁串行化并以原子替换落盘。

**Tech Stack:** Python 3.12+、现有 `garminconnect` 客户端、标准库 `argparse`/`pathlib`/`fcntl`/`json`/`logging`、pytest、Ruff、Mypy。

**Spec:** `docs/superpowers/specs/2026-11-27-garmin-daily-ledger-design.md`

## Global Constraints

- 强制使用 `uv`。
- Python 强制类型标注；所有 API 调用与文件操作必须有异常处理。
- 不读取、修改、打印或提交 `.env`、`secrets.json`、`cookies.json` 或 Garmin token。
- 台账与日志默认位于 `~/.garmin-mcp-lite/`，不进入 Git。
- 目录权限 `0700`，文件权限 `0600`；日志脱敏并轮转。
- 保持 `fail_under = 100`。
- 一文件一提交；但本功能未获得用户明确提交授权前，只修改与测试，不执行 `git commit`。
- 所有实现位于 `feat/garmin-daily-ledger` worktree。

## Review Focus

- 10:00 尚未同步：核心 HRV/睡眠缺失时必须标记失败且不能编造数值。
- 晚间历史日期补跑：活动按历史日期读取，训练状态必须标注为“运行时当前状态”。
- 单项活动详情失败：保留活动摘要与其他活动，不能丢弃整天结果。
- JSON/Markdown 部分写入或同日并发：JSON 为权威数据，文件锁串行化，Markdown 可由 JSON 重建。
- 异常文本泄露：持久化前脱敏，日志不得包含 token、请求头或完整原始载荷。

---

### Task 1: 晨间与晚间数据收集

**Files:**
- Create: `garmin_mcp_lite/ledger.py`
- Create: `tests/test_ledger.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `hrv.get_hrv_status(date)`、`health.get_health_data("sleep", date)`、`activities.get_activity_detail(activity_id)`、`training.get_training_status()`、`client.get_activities_by_date(start, end)`、`_common.summarize_activity()`。
- Produces: `collect_morning(date: str) -> dict[str, Any]`、`collect_evening(date: str) -> dict[str, Any]`、`run_ledger(mode: Literal["morning", "evening"], date: str) -> dict[str, Any]`。

- [ ] **Step 1: Write failing collection tests**

创建 `tests/test_ledger.py`，使用 `mock_get_client` 覆盖：

```python
def test_collect_morning_combines_hrv_and_sleep(mock_get_client):
    mock_get_client.get_hrv_data.return_value = {
        "hrvSummary": {
            "calendarDate": "2026-11-27",
            "status": "BALANCED",
            "weeklyAvg": 55,
            "lastNightAvg": 58,
            "baseline": {"balancedLow": 45, "balancedUpper": 65},
        }
    }
    mock_get_client.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "sleepScore": 82,
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

    result = collect_morning("2026-11-27")

    assert result["hrv"]["status"] == "BALANCED"
    assert result["sleep"]["duration_min"] == 438
    assert result["analysis"]["recovery_focus"] is False
```

同时为以下场景写失败测试：

- `test_collect_morning_marks_missing_hrv_as_failure`
- `test_collect_morning_marks_sleep_error_as_failure`
- `test_collect_evening_aggregates_all_activities_without_limit`
- `test_collect_evening_keeps_summary_when_detail_fails`
- `test_collect_evening_labels_training_status_as_current`
- `test_run_ledger_rejects_unknown_mode`

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_ledger.py`
Expected: FAIL，原因应为 `garmin_mcp_lite.ledger` 尚不存在。

- [ ] **Step 3: Implement collection functions in `garmin_mcp_lite/ledger.py`**

实现：

```python
def collect_morning(date: str) -> dict[str, Any]: ...
def collect_evening(date: str) -> dict[str, Any]: ...
def run_ledger(mode: Literal["morning", "evening"], date: str) -> dict[str, Any]: ...
```

要求：

- 晨间调用现有 HRV/睡眠工具，识别 `{"error": ...}` 与 `{"sleep": {"error": ...}}`。
- 晚间直接调用 `client.get_activities_by_date(date, date)` 获取全量活动，不使用带 `limit` 的摘要工具。
- 每项活动先 `summarize_activity()`，再调用 `get_activity_detail()`；详情失败写入该项 `detail_error`。
- 训练状态放入 `training_status_current`，并包含 `as_of` 时间戳。
- 任何核心数据源失败时，结果包含 `status: "partial"` 或 `"unavailable"` 与脱敏错误。

- [ ] **Step 4: Add ledger module to autouse client patching**

在 `tests/conftest.py` 的 `_TOOL_MODULES` 中加入 `"garmin_mcp_lite.ledger"`，防止测试访问真实 token。

- [ ] **Step 5: Run collection tests**

Run: `uv run pytest -q tests/test_ledger.py`
Expected: PASS。

### Task 2: 台账持久化与 Markdown 渲染

**Files:**
- Modify: `garmin_mcp_lite/ledger.py`
- Modify: `tests/test_ledger.py`

**Interfaces:**
- Consumes: Task 1 的结构化结果。
- Produces: `LedgerStore` 类，公开 `write(date: str, mode: Literal["morning", "evening"], payload: dict[str, Any]) -> tuple[Path, Path]`；`render_markdown(document: dict[str, Any]) -> str`。

- [ ] **Step 1: Write failing persistence tests**

新增测试：

- `test_write_creates_private_json_and_markdown`
- `test_same_slot_rerun_replaces_without_duplicate_section`
- `test_morning_and_evening_merge_into_same_day`
- `test_markdown_is_rebuilt_from_json_when_missing`
- `test_atomic_write_leaves_previous_file_on_failure`
- `test_concurrent_writes_preserve_both_slots`
- `test_log_sanitizes_token_like_error_text`

断言目录/文件模式分别为 `0o700`/`0o600`，Markdown 包含“晨间记录”“晚间复盘”，JSON 可由 `json.loads` 还原。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_ledger.py -k 'write or markdown or concurrent or atomic or private or log'`
Expected: FAIL，原因应为持久化接口尚不存在。

- [ ] **Step 3: Implement `LedgerStore` and renderer**

实现：

```python
class LedgerStore:
    def __init__(self, root: Path | None = None) -> None: ...
    def write(
        self,
        date: str,
        mode: Literal["morning", "evening"],
        payload: dict[str, Any],
    ) -> tuple[Path, Path]: ...
```

要求：

- 默认根目录由 `GARMIN_LEDGER_DIR` 或 `~/.garmin-mcp-lite/ledger` 解析。
- 使用 `fcntl.flock()` 对 `YYYY-MM-DD.lock` 加锁。
- JSON 先原子写入，再由 JSON 渲染并原子写入 Markdown。
- 同 slot 更新、异 slot 合并；保留 `generated_at`。
- 临时文件与目标同目录，`os.replace()` 原子替换。
- 创建目录时显式 `mode=0o700`，文件写入后 `chmod(0o600)`。
- 日志使用 `logging.handlers.RotatingFileHandler`，格式化前调用脱敏函数。

- [ ] **Step 4: Run persistence tests**

Run: `uv run pytest -q tests/test_ledger.py -k 'write or markdown or concurrent or atomic or private or log'`
Expected: PASS。

### Task 3: CLI 与退出码

**Files:**
- Modify: `garmin_mcp_lite/ledger.py`
- Modify: `tests/test_ledger.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `main(argv: Sequence[str] | None = None) -> int`；脚本入口 `garmin-mcp-lite-ledger = "garmin_mcp_lite.ledger:main"`。

- [ ] **Step 1: Write failing CLI tests**

新增测试：

- `test_cli_morning_writes_today_by_default`
- `test_cli_evening_accepts_explicit_date`
- `test_cli_success_returns_zero`
- `test_cli_partial_returns_nonzero_but_writes_ledger`
- `test_cli_invalid_date_returns_two`
- `test_cli_ledger_dir_override`

使用 `monkeypatch.setattr(ledger, "today_str", lambda: "2026-11-27")` 与临时目录。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_ledger.py -k cli`
Expected: FAIL，原因应为 `main` 尚不存在。

- [ ] **Step 3: Implement CLI in `garmin_mcp_lite/ledger.py`**

使用 `argparse` 创建 `morning`/`evening` 子命令，支持：

```text
--date YYYY-MM-DD
--ledger-dir PATH
```

流程：解析日期 → `run_ledger()` → `LedgerStore.write()` → 根据 `status` 返回 0/1；参数错误返回 2。所有异常写入脱敏日志并返回 1。

- [ ] **Step 4: Register console script in `pyproject.toml`**

在 `[project.scripts]` 增加：

```toml
garmin-mcp-lite-ledger = "garmin_mcp_lite.ledger:main"
```

- [ ] **Step 5: Run CLI tests**

Run: `uv run pytest -q tests/test_ledger.py -k cli`
Expected: PASS。

### Task 4: 全量验证与真实只读冒烟测试

**Files:**
- Modify: `tests/test_ledger.py`（仅在被覆盖报告证明有必要时）

**Interfaces:**
- Consumes: Tasks 1–3 的完整实现。
- Produces: 可发布代码与验证证据。

- [ ] **Step 1: Run full suite with coverage**

Run: `uv run pytest -q --cov`
Expected: 全部通过，覆盖率 100.00%，无遗漏语句。

- [ ] **Step 2: Run lint and type checks**

Run:

```bash
uv run ruff check .
uv run mypy garmin_mcp_lite
```

Expected: Ruff 无错误；Mypy 无问题。

- [ ] **Step 3: Run real read-only smoke test**

Run:

```bash
uv run garmin-mcp-lite-ledger morning --ledger-dir /tmp/garmin-ledger-smoke
uv run garmin-mcp-lite-ledger evening --ledger-dir /tmp/garmin-ledger-smoke
```

Expected: 两条命令退出码为 0，生成当日 JSON/Markdown；输出与日志不包含 token 或密码。

- [ ] **Step 4: Review diff**

Run: `git diff --check && git status --short`
Expected: 无空白错误；只包含设计稿、计划、实现、测试、入口与文档相关文件。

### Task 5: 文档与 Qoder Automations

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Consumes: 已完成的 CLI。
- Produces: 用户可复现的运行说明与两条自动化配置。

- [ ] **Step 1: Inspect existing documentation checks**

Run: `uv run pytest -q tests/test_server.py tests/test_readme.py`（若 `tests/test_readme.py` 不存在则只运行前者）。
Expected: 现有通过；记录需要在 Task 5 Step 2 同步更新的命令或工具数量断言。

- [ ] **Step 2: Document CLI and schedules**

在中英文 README 增加：

- `garmin-mcp-lite-ledger morning|evening` 用法。
- 默认台账与日志目录、权限、补跑方式。
- Qoder Desktop 本地自动化：每天 10:00 与 22:00，Asia/Shanghai。
- Qoder 必须运行、Keep device awake、Execution authorization 与 Run history 检查方式。

- [ ] **Step 3: Create Qoder automations after code verification**

在 Qoder Desktop 的 Automations 中创建：

1. `Garmin 晨间恢复台账`：每天 10:00，Asia/Shanghai，本地运行，工作目录为项目主目录，执行 `uv run garmin-mcp-lite-ledger morning`。
2. `Garmin 晚间训练复盘`：每天 22:00，Asia/Shanghai，本地运行，工作目录同上，执行 `uv run garmin-mcp-lite-ledger evening`。

Prompt 必须包含：只运行上述命令；检查退出码和当日 Markdown；禁止读取或输出凭据；失败时只报告脱敏错误。

- [ ] **Step 4: Verify automation configuration**

打开两个自动化详情，确认执行位置、时区、下次执行时间、工作目录与授权范围；在 Run history 中确认首次手动运行结果。
