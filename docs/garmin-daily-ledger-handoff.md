# Garmin 每日训练台账交接文档

> 适用分支：`feat/garmin-daily-ledger`  
> 工作树：`/Users/hainingyu/Code/garmin_mcp_lite/.worktrees/feat-garmin-daily-ledger`  
> 交接日期：2026-11-28  
> 当前状态：功能、测试和真实只读冒烟验证已完成；变更尚未提交或合并。

## 1. 这套台账解决什么问题

每天两次在本机读取 Garmin Connect 数据并生成可追溯的训练记录：

- **晨间记录**：按 Garmin 起床日期读取昨晚 HRV 与睡眠，记录恢复信号。
- **晚间复盘**：按活动日期汇总当天全部活动、训练负荷、训练效果，并附带运行时当前训练状态。
- **本地持久化**：JSON 是权威数据，Markdown 是人类可读报告。
- **定时执行**：由 Qoder Desktop 本地自动化触发，不依赖 MCP 客户端。

台账只读取 Garmin 数据，不修改云端活动、训练计划或身体数据，也不替代医疗诊断。

## 2. 代码与成果位置

| 内容 | 位置 |
|:---|:---|
| CLI、数据收集、分析、渲染、存储、日志 | `garmin_mcp_lite/tools/ledger.py` |
| 回归测试 | `tests/test_ledger.py` |
| 测试客户端模拟注册 | `tests/conftest.py` |
| 命令入口 | `pyproject.toml` 的 `garmin-mcp-lite-ledger` |
| 中文使用说明 | `README.zh-CN.md` |
| 英文使用说明 | `README.md` |
| 设计稿 | `docs/superpowers/specs/2026-11-27-garmin-daily-ledger-design.md` |
| 实施计划与进度账本 | `docs/superpowers/plans/2026-11-27-garmin-daily-ledger.md`、`.superpowers/sdd/2026-11-27-garmin-daily-ledger/progress.md` |
| 默认台账目录 | `~/.garmin-mcp-lite/ledger/` |
| 默认日志目录 | `~/.garmin-mcp-lite/logs/` |

核心入口是 `garmin_mcp_lite.tools.ledger:main`。日常使用不需要启动 MCP server。

## 3. 快速开始

### 3.1 进入功能工作树

```bash
cd /Users/hainingyu/Code/garmin_mcp_lite/.worktrees/feat-garmin-daily-ledger
```

### 3.2 查看命令帮助

```bash
uv run garmin-mcp-lite-ledger --help
uv run garmin-mcp-lite-ledger morning --help
uv run garmin-mcp-lite-ledger evening --help
```

支持的命令形式：

```text
garmin-mcp-lite-ledger morning [--date YYYY-MM-DD] [--ledger-dir PATH]
garmin-mcp-lite-ledger evening [--date YYYY-MM-DD] [--ledger-dir PATH]
```

### 3.3 记录今天

```bash
uv run garmin-mcp-lite-ledger morning
uv run garmin-mcp-lite-ledger evening
```

命令成功时会打印 JSON 和 Markdown 的实际路径。只有 `status = success` 时退出码才是 `0`。

### 3.4 补跑历史日期

```bash
uv run garmin-mcp-lite-ledger morning --date 2026-11-27
uv run garmin-mcp-lite-ledger evening --date 2026-11-27
```

- 晨间 `--date` 表示 Garmin 的起床日期。
- 晚间 `--date` 只约束活动列表；训练状态、准备度和四周负荷始终是**运行时当前状态**，不是历史当天状态。

### 3.5 使用临时目录验证

```bash
uv run garmin-mcp-lite-ledger morning --ledger-dir /tmp/garmin-ledger-smoke
uv run garmin-mcp-lite-ledger evening --ledger-dir /tmp/garmin-ledger-smoke
```

适合演练或排障，不会改动默认台账目录。

## 4. 晨间记录怎么理解

晨间记录合并两类数据：

- `hrv.get_hrv_status(date)`：HRV 状态、昨晚平均值、周平均、个人基线和训练建议。
- `health.get_health_data("sleep", date)`：睡眠评分、质量、总时长、深睡、浅睡、REM、清醒和静息心率等。

### 4.1 状态含义

| 状态 | 含义 |
|:---|:---|
| `success` | HRV 与睡眠核心数据都有效 |
| `partial` | 只有一项核心数据有效 |
| `unavailable` | HRV 与睡眠都没有有效核心数据 |

### 4.2 恢复结论规则

代码不会把“数据缺失”解释成“状态正常”：

- HRV 为 `UNBALANCED`、`LOW`、`POOR`，或睡眠质量为 `FAIR`、`POOR`：标记恢复优先。
- 只有在两项数据都完整，且 HRV 为 `BALANCED`、睡眠质量为 `GOOD` 或 `EXCELLENT` 时，才输出正常训练日。
- 其他情况输出数据不足；如果同时存在明确恢复信号，仍保留恢复优先，并标注为部分数据结论。

### 4.3 10:00 还没同步怎么办

如果晨间自动化早于手表同步，出现 `partial` 或 `unavailable` 是预期行为。等待 Garmin Connect 同步后，手动补跑同一天：

```bash
uv run garmin-mcp-lite-ledger morning --date YYYY-MM-DD
```

已有成功记录不会被后续失败或部分成功覆盖。

## 5. 晚间复盘怎么理解

晚间复盘包含：

- 指定日期的全部活动，不使用带 `limit` 的摘要工具。
- 每项活动的类型、距离、时长、平均心率、配速、训练负荷和有氧/无氧训练效果。
- 总距离、总时长、总训练负荷及负荷是否完整。
- 运行时当前训练状态、急性负荷、ACWR、四周负荷目标和准备度。

### 5.1 历史日期补跑的边界

假设补跑 `2026-11-20`：

- 活动列表和活动汇总来自 `2026-11-20`。
- `training_status_current` 来自执行命令时的当前 Garmin 状态。
- Markdown 明确显示“运行时当前训练状态”和“状态采集时间”。

不要把历史晚间台账中的当前训练状态当成历史当天的状态。

### 5.2 单项活动详情失败

某项活动详情请求失败时：

- 保留该活动的列表摘要。
- 保留其他活动。
- 在该活动下记录 `detail_error`。
- 整天状态标记为 `partial`。
- 如果负荷不完整，总训练负荷可能为 `null`，且 `training_load_complete = false`。

### 5.3 没有活动

`activity_count = 0` 表示当天没有记录到活动。当前 Markdown 尚未输出单独的“当天无记录活动”句子，这是已知的小项改进点。

## 6. 输出文件与数据结构

### 6.1 文件命名

```text
~/.garmin-mcp-lite/ledger/YYYY-MM-DD.json
~/.garmin-mcp-lite/ledger/YYYY-MM-DD.md
~/.garmin-mcp-lite/ledger/YYYY-MM-DD.lock
~/.garmin-mcp-lite/logs/ledger.log
```

- JSON：权威数据，适合后续分析。
- Markdown：由 JSON 渲染，适合直接阅读。
- `.lock`：同日写入锁文件，不需要手动删除。

### 6.2 JSON 顶层结构

```json
{
  "date": "YYYY-MM-DD",
  "updated_at": "ISO-8601 timestamp",
  "morning": {
    "date": "YYYY-MM-DD",
    "status": "success | partial | unavailable",
    "generated_at": "ISO-8601 timestamp",
    "hrv": {},
    "sleep": {},
    "analysis": {
      "recovery_focus": true,
      "summary": "Recovery-first day",
      "signals": []
    },
    "errors": []
  },
  "evening": {
    "date": "YYYY-MM-DD",
    "status": "success | partial | unavailable",
    "generated_at": "ISO-8601 timestamp",
    "activity_count": 0,
    "totals": {
      "distance_km": 0,
      "duration_min": 0,
      "training_load": 0,
      "training_load_complete": true
    },
    "activities": [],
    "training_status_current": {
      "as_of": "ISO-8601 timestamp"
    },
    "errors": []
  }
}
```

`morning` 或 `evening` 可能尚未生成；JSON 中只包含已经写入的时段。

### 6.3 查看状态而不输出健康明细

```bash
TODAY=$(date +%F)
LEDGER="$HOME/.garmin-mcp-lite/ledger/$TODAY.json"

jq '{
  date,
  morning_status: .morning.status,
  evening_status: .evening.status,
  morning_errors: .morning.errors,
  evening_errors: .evening.errors
}' "$LEDGER"
```

打开可读报告：

```bash
open "$HOME/.garmin-mcp-lite/ledger/$TODAY.md"
```

## 7. 退出码与失败语义

| 退出码 | 含义 |
|:---|:---|
| `0` | 本次时段数据完整，JSON 和 Markdown 写入成功 |
| `1` | 数据部分成功、不可用、日志初始化失败或文件写入失败 |
| `2` | 参数错误，例如缺少子命令或日期格式不合法 |

注意：`1` 不代表完全没有成果。`partial` 仍会保存已成功获取的数据，并记录脱敏错误。

## 8. 存储、并发与隐私

### 8.1 存储保证

- 同日写入使用 `fcntl.flock()` 串行化。
- JSON 和 Markdown 使用同目录临时文件、`fsync` 和 `os.replace()` 原子写入。
- JSON 是 canonical 数据源；Markdown 丢失或内容过期时，会从 JSON 重建。
- 同一时段成功重复运行会更新该时段，不会产生重复 Markdown 段落。
- 已有成功记录不会被失败或部分成功覆盖。

### 8.2 权限

- 台账与日志目录：`0700`
- JSON、Markdown、锁文件和日志：`0600`

检查权限：

```bash
stat -f '%Sp %N' \
  "$HOME/.garmin-mcp-lite/ledger" \
  "$HOME/.garmin-mcp-lite/logs"
```

### 8.3 日志与脱敏

- 日志按大小轮转：单文件约 1 MB，保留 3 个备份。
- 错误文本会脱敏 `Authorization`、`Bearer`、`Basic`、`Cookie`、`Set-Cookie`、token、password、API key、session id 等字段。
- 原始 JSON/类载荷错误不会持久化，只保留 `<redacted>`。
- 不要读取、打印、复制或提交 `.env`、`secrets.json`、`cookies.json` 或 Garmin token。

### 8.4 自定义目录

```bash
export GARMIN_LEDGER_DIR="$HOME/garmin-ledger-custom"
export GARMIN_LOG_DIR="$HOME/garmin-ledger-logs"
```

也可以只为单次命令指定台账目录：

```bash
uv run garmin-mcp-lite-ledger morning --ledger-dir "$HOME/garmin-ledger-custom"
```

## 9. Qoder Desktop 自动化

### 9.1 预期配置

| 名称 | 时间 | 时区 | 执行命令 |
|:---|:---|:---|:---|
| `Garmin 晨间恢复台账` | 每天 10:00 | `Asia/Shanghai` | `uv run --directory /Users/hainingyu/Code/garmin_mcp_lite/.worktrees/feat-garmin-daily-ledger garmin-mcp-lite-ledger morning` |
| `Garmin 晚间训练复盘` | 每天 22:00 | `Asia/Shanghai` | `uv run --directory /Users/hainingyu/Code/garmin_mcp_lite/.worktrees/feat-garmin-daily-ledger garmin-mcp-lite-ledger evening` |

### 9.2 自动化 Prompt 必须包含

- 只运行对应的一条台账命令。
- 检查退出码必须为 `0`。
- 确认当天 Markdown 存在；晚间还需包含“晚间复盘”。
- 禁止读取或输出 Garmin token、密码、cookies 或其他凭据。
- 禁止修改 Garmin 云端数据。
- 失败时只报告脱敏错误和失败步骤，不输出原始异常载荷。

### 9.3 运行条件

- Qoder Desktop 在计划时间保持运行。
- 按需开启 **Keep device awake**。
- 使用 **Auto Approval** 或所需执行授权。
- 在 **Automations → Run history** 检查每次结果。

### 9.4 交接时的自动化检查

2026-11-28 的检查中，晨间自动化存在、启用且最近一次手动执行成功。当前自动化列表未显示晚间任务；交接后应再次打开 Qoder Automations 确认。如果晚间任务缺失，按上表重建，不要创建重复任务。

## 10. 验证与测试

在功能工作树执行：

```bash
uv run pytest -q --cov
uv run ruff check .
uv run mypy garmin_mcp_lite
uv build
git diff --check
```

2026-11-28 最终验证结果：

- `504 passed`
- 覆盖率 `100.00%`
- Ruff 通过
- Mypy 通过
- `uv build` 通过
- `git diff --check` 通过
- 真实 Garmin 晨间和晚间只读冒烟测试均退出 `0`

只验证台账模块：

```bash
uv run pytest -q tests/test_ledger.py
```

## 11. 常见问题排查

| 现象 | 优先检查 | 处理 |
|:---|:---|:---|
| `Garmin token not found` | 本机是否已有登录会话 | 运行 `uv run garmin-mcp-lite-login`，按提示完成登录 |
| 晨间 `partial` / `unavailable` | 手表是否已同步、日期是否为起床日期 | 等待同步后补跑同一天 |
| 晚间 `partial` | 某个活动详情或当前训练状态请求失败 | 查看脱敏错误；保留已有摘要，稍后重跑 |
| 历史日期训练状态看起来不对 | 是否把运行时当前状态当成历史状态 | 查看 `as_of` 和 Markdown 的“运行时当前训练状态” |
| JSON 已更新但 Markdown 是旧内容 | Markdown 是否曾写入失败 | 再运行任意时段；代码会从 JSON 修复 Markdown |
| 自动化失败但手动命令成功 | Qoder 执行目录、权限、任务是否启用 | 检查 Run history、工作目录和 Execution authorization |
| 文件权限不对 | 是否被手动改过 | 重新运行命令；代码会恢复目录 `0700`、文件 `0600` |
| 日期格式错误 | 是否使用 `YYYY-MM-DD` | 改用规范日期，例如 `2026-11-28` |

## 12. 交接清单

- [ ] 决定是否提交、合并或创建 PR；当前分支尚无提交。
- [ ] 确认 Qoder 中晨间和晚间两个自动化都存在且启用。
- [ ] 在 Automations → Run history 各手动运行一次。
- [ ] 确认当天 JSON 中晨间和晚间状态都是 `success`。
- [ ] 确认 Markdown 同时包含“晨间记录”和“晚间复盘”。
- [ ] 确认目录 `0700`、文件 `0600`，日志中无凭据。
- [ ] 如需长期运行，保持 Qoder Desktop 开机并按需开启 Keep device awake。

## 13. 已知改进项

以下事项不影响当前核心流程，可在后续迭代处理：

- `_parse_date` 仍可能接受 `2026-1-1` 这类非规范日期。
- 无活动晚间 Markdown 尚未输出单独的“当天无记录活动”句子。
- 顶层收集异常会写入台账，但存储前未额外记录日志。
- README 仍有少量旧工具数量引用，且只读/写入数量需要统一为 29 个工具总数。
