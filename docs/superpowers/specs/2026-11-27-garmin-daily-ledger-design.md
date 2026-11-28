# Garmin 每日晨间台账与晚间复盘自动化设计

## 目标

每天自动完成两次本地记录：

- 10:00（Asia/Shanghai）：拉取昨晚 HRV 与睡眠数据，生成恢复分析并写入晨间台账。
- 22:00（Asia/Shanghai）：拉取当天训练活动、训练负荷、训练效果和当前训练状态，生成晚间复盘。

用于持续观察恢复与训练趋势，不替代医疗诊断，不自动修改 Garmin 数据，也不向外部服务发布内容。

## 约束

- 复用现有 `garmin_mcp_lite` 客户端和工具函数。
- 只使用本机已有 Garmin token，不读取、打印或复制凭据。
- 本地执行，默认工作目录为项目目录。
- 所有文件与网络调用必须有异常处理；失败不能覆盖已有成功记录。
- 保持 100% 测试覆盖率门禁。

## 方案选择

### 方案 A：确定性本地 CLI + Qoder Automations（采用）

新增本地台账 CLI，由两个 Qoder 本地自动化按固定时间调用。数据抓取与文件格式由代码控制，Agent 只负责触发和汇总，行为稳定、可测试、可重放。

优点：复用现有客户端、输出一致、失败可观测、不依赖 Agent 临时判断。
缺点：需要先实现 CLI；Qoder 必须在计划时间运行。

### 方案 B：纯 Qoder Agent 自动化

每天由 Agent 自行调用 MCP 工具、分析并写文件。

优点：实现快；缺点：输出格式与调用步骤可能漂移，难以稳定回归测试，不适合长期台账。

### 方案 C：macOS launchd

使用系统级定时器直接运行脚本。

优点：不依赖 Qoder 运行；缺点：与用户选择的 Qoder 自动化入口不一致，状态查看和授权体验分散。

## 详细设计

### CLI

新增 `garmin-mcp-lite-ledger` 命令，支持：

```bash
garmin-mcp-lite-ledger morning [--date YYYY-MM-DD]
garmin-mcp-lite-ledger evening [--date YYYY-MM-DD]
```

- 默认日期为当天；`--date` 用于补跑。
- 晨间 `--date` 表示 Garmin 的起床日期，HRV 与睡眠均按该日期读取。
- 晚间 `--date` 只约束当天活动列表；训练状态、准备度和负荷始终表示“运行时的当前状态”，并在输出中明确标注，避免把当前数据伪装成历史数据。
- 每次运行写入 JSON 与 Markdown。
- 同一日期、同一时段重复运行时合并更新，不产生重复段落。
- 退出码：成功为 0，数据或文件写入失败为非 0，供 Qoder Run history 判断。

### 晨间记录

复用：

- `hrv.get_hrv_status(date)`：HRV 状态、昨晚平均值、周平均、个人基线区间与建议。
- `health.get_health_data("sleep", date)`：睡眠评分、总时长、各分期、清醒、静息心率、夜间 HRV、SpO2、呼吸与压力。

分析规则：

- HRV 为 `BALANCED` 且 Garmin 睡眠评分为正常/优秀：正常训练日。
- HRV 为 `UNBALANCED` 或 `LOW/POOR`：标记恢复优先，建议降低强度。
- 睡眠评分较低时叠加恢复提示；睡眠时长只记录和展示，不设置未个性化的医学阈值。
- 数据缺失时明确写“数据不足”，不推断数值。

### 晚间记录

复用：

- 活动列表通过 `client.get_activities_by_date(date, date)` 获取全量结果，不使用带 `limit` 的摘要工具，避免总数和汇总被截断。
- `activities.get_activity_detail(activity_id)`：训练负荷与有氧/无氧训练效果。
- `training.get_training_status()`：当前训练状态、急性负荷、ACWR、四周负荷与准备度。

输出：

- 当天活动数量与总距离/总时长。
- 每项活动的类型、距离、时长、平均心率、配速、训练负荷与训练效果。
- 当前训练状态、急性负荷、ACWR、四周负荷目标与准备度摘要；该区块标注为“运行时的当前状态”。
- 无活动时明确写“当天无记录活动”。
- 单项活动详情失败时保留活动摘要，并在该项下记录错误，不丢弃其他活动。

### 存储

默认目录：

```text
~/.garmin-mcp-lite/ledger/
~/.garmin-mcp-lite/logs/
```

每日文件：

```text
ledger/YYYY-MM-DD.json
ledger/YYYY-MM-DD.md
logs/ledger.log
```

- JSON 保存完整结构化结果，便于后续分析，并作为 canonical 数据源。
- Markdown 保存人类可读台账，按“晨间记录”和“晚间复盘”分区。
- 同一日期写入使用文件锁串行化，避免晨间与晚间补跑互相覆盖。
- 写入采用同文件系统临时文件 + 原子替换；JSON 成功而 Markdown 失败时，下次运行从 canonical JSON 重建 Markdown。
- 台账与日志目录权限为 `0700`，文件权限为 `0600`。
- 日志不记录 token、密码、请求头或完整原始 API 载荷；异常消息写入前进行脱敏。
- 日志按大小轮转，台账默认不自动删除；未来如需保留期限，由用户明确指定。

### Qoder 自动化

创建两个本地自动化：

1. `Garmin 晨间恢复台账`
   - Schedule：每天 10:00，Asia/Shanghai。
   - Work folder：`/Users/hainingyu/Code/garmin_mcp_lite`。
   - Prompt：运行 `uv run garmin-mcp-lite-ledger morning`，检查退出码与当日 Markdown，禁止读取或输出凭据。
2. `Garmin 晚间训练复盘`
   - Schedule：每天 22:00，Asia/Shanghai。
   - Work folder：同上。
   - Prompt：运行 `uv run garmin-mcp-lite-ledger evening`，检查退出码与当日 Markdown，禁止读取或输出凭据。

运行条件：

- Qoder Desktop 保持运行。
- 开启 Keep device awake，减少睡眠错过。
- 本地自动化启用 Execution authorization，仅授予项目运行所需权限。
- 每次执行后在 Automations → Run history 检查结果。

## 非目标

- 不自动同步到 Git、云盘或笔记软件。
- 不发送微信、邮件或其他通知。
- 不自动修改训练计划、活动或身体数据。
- 不做医学诊断。

## 失败语义

- `unavailable`：核心数据源不可用且没有任何有效内容；退出码为非 0。
- `partial`：至少一个区块失败，但其他区块成功；写入失败区块与错误摘要，退出码为非 0，便于 Qoder 标记需要检查。
- `success`：所有请求区块均有有效结果；退出码为 0。
- 训练状态中的可选字段为 `None` 属于数据缺失，不自动视为请求失败；只有明确错误或核心活动列表请求失败才按失败处理。
- 10:00 未同步导致晨间数据不足时，不自动反复请求；可在数据同步后手动执行 `morning --date YYYY-MM-DD` 补跑。

## 测试计划

- 使用假客户端验证晨间与晚间数据组装。
- 时钟、日期和工具依赖通过参数或模块级函数注入，确保默认日期与补跑可测试。
- 将新模块加入测试客户端的 autouse patch 范围，防止测试访问真实 token。
- 验证缺失数据、API 异常、部分活动详情失败与退出码。
- 验证 JSON/Markdown 写入、重复运行合并、JSON 重建 Markdown、文件锁、原子替换和并发运行。
- 验证目录/文件权限、日志脱敏与轮转。
- 运行全量 `pytest --cov`，保持 100% 覆盖率。
- 运行 Ruff 与 Mypy。
- 使用真实 Garmin 客户端做一次只读冒烟测试，不打印敏感信息。
