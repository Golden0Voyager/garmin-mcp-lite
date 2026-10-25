# Garmin MCP Lite

<!-- AI CONTEXT START -->
> **[写给 AI 助手与 LLM]** 
> 你当前正在连接一个 Garmin MCP (Model Context Protocol) 服务器。
> 1. **数据新鲜度**：当用户询问其最近的运动或健康指标时，务必主动调用接口获取最新数据，不要使用陈旧上下文。
> 2. **参数调优**：在调用 `garmin_activity_detail` 等工具时，使用 `fields` 参数来限制返回的载荷大小，以节省上下文窗口（例如：`["splits", "hrZones"]`）。
> 3. **大部分只读**：17 个工具只读；两个会写入体重数据（`garmin_add_body_composition`、`garmin_sync_weight`）。调用前先和用户确认数字，同步先用 `dry_run=true` 试跑 —— 写入无法撤销。
> 4. **禁止索要密码**：绝对不要向用户索要他们的 Garmin 密码。身份验证已在外部通过本地 Token 安全完成。
> 5. **区间解读**：`garmin_activity_detail` 返回的心率区间只有秒数、没有边界。判断强度前先调用 `garmin_zones` 拿到各区间 bpm 范围。
> 6. **状态自检**：`garmin_status` 报告一次性登录（Garmin 必需，小米可选）是否有效，并给出失效时要跑的确切命令。排查任何认证问题前先调它。
<!-- AI CONTEXT END -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/garmin-mcp-lite.svg)](https://badge.fury.io/py/garmin-mcp-lite)

*Read this in other languages: [English](README.md), [简体中文](README.zh-CN.md).*

精简版 Garmin MCP 服务器，专为耐力运动爱好者设计。

提取了进行深度运动数据分析最核心的 19 个接口（涵盖跑步、骑行、游泳、健康及体成分数据），完美替代臃肿的 80+ 接口方案。

其中 17 个是只读，两个会写入：`garmin_add_body_composition` 记一条手动体重，`garmin_sync_weight` 从小米体脂秤拉取 —— 因为 Garmin 没有接收第三方体重秤数据的入口。

## 核心工具（19 个替代 80+）

### 🔧 状态自检

| 工具 | 功能 |
|:---|:---|
| `garmin_status` | 检查两个一次性登录（Garmin 必需、小米可选）是否就位且有效，缺失或失效时给出下一步要跑的确切命令 |

### 🏃 活动与训练

| 工具 | 功能 |
|:---|:---|
| `garmin_activities` | 查跑步/骑行/游泳/潜水记录，支持日期/类型筛选 |
| `garmin_activity_detail` | 单次活动详情（配速、心率区间、分段、圈数） |
| `garmin_training_plan` | 今日/指定日期训练课表 |
| `garmin_training_status` | 训练状态、VO2Max、**急性负荷**、**负荷分布**、恢复时间、训练准备度 |
| `garmin_weekly_stats` | 周/月/年训练总量统计 |
| `garmin_coach` | Garmin Coach 训练计划概览 |
| `garmin_race_prediction` | 5K/10K/半马/全马成绩预测（含配速），可看 90 天或 1 年内的变化 |
| `garmin_personal_records` | 个人纪录：1K 到全马、最长跑/骑行、游泳、步数纪录，附创造纪录的活动 |

### 💚 健康

| 工具 | 功能 |
|:---|:---|
| `garmin_health` | 睡眠/HRV/压力/身体电量/血氧/呼吸/强度分钟/步数/爬楼层/静息心率，支持 `metric` 参数定向查询 |
| `garmin_hr_trend` | 近 7/30/90 天静息心率趋势 |
| `garmin_zones` | 各运动的心率区间边界（bpm）、乳酸阈值、FTP；用于解读 `garmin_activity_detail` 的 `hrZones` |

### ⚖️ 体重与体成分

| 工具 | 功能 |
|:---|:---|
| `garmin_body_composition` | 体重与体成分历史：体重、BMI、体脂率、体水分、肌肉量、骨量、内脏脂肪、代谢年龄。质量统一换算为千克，未测量的字段直接省略 |
| `garmin_add_body_composition` | **写入**一条测量记录（体重必填，其余可选）。以 FIT 体成分文件上传，与 Garmin 自家 Index 体脂秤走同一条通道 |
| `garmin_sync_weight` | **写入**小米体脂秤的称重记录到 Garmin。只补 Garmin 还没有的天，因此可重复执行。需先跑一次 `garmin-mcp-lite-xiaomi-login` |

> **`garmin_add_body_composition` 会写入你的 Garmin 账号**，本工具没有撤销能力。Garmin 不去重，同一天调用两次可能留下两条记录 —— 若当天已有数据，返回结果会带 `warning`。`weight` 单位是**千克**，超过 500 会被判定为误传克值并拒绝：读取接口在 API 层返回的是克，读改写是最容易踩的坑。Garmin 的上传接口不一定会返回状态，因此工具会回读当天数据，只有存储值与提交值一致时才返回 `verified: true`。

### 🎯 目标与挑战

| 工具 | 功能 |
|:---|:---|
| `garmin_events` | 赛事日历：仅未来的比赛（按日期升序），目标距离、目标完赛时间 |
| `garmin_challenges` | 进行中的挑战：虚拟攀登、月度徽章及完成度 |

### ⌚ 设备与装备

| 工具 | 功能 |
|:---|:---|
| `garmin_gear` | 跑鞋/自行车装备库及真实累计里程 |
| `garmin_device` | 设备信息：固件版本、更新可用性、主设备状态、注册日期 |

## 快速开始

两种运行方式。**推荐装成常驻命令** —— 启动远低于 1 秒、不需要联网、GUI 客户端也能找到它。`uvx` 也能用，但首次运行要下载依赖，而且对不继承 shell `PATH` 的客户端不可见。

### 1. 安装

```bash
uv tool install garmin-mcp-lite
which garmin-mcp-lite     # → ~/.local/bin/garmin-mcp-lite
```

<details>
<summary>备选：不安装，直接用 <code>uvx</code> 运行</summary>

```bash
uvx garmin-mcp-lite
```

适合 Claude Code、Codex CLI 这类终端客户端。GUI 客户端为什么通常需要绝对路径，见[常见问题](#常见问题)。
</details>

### 2. 账号认证（仅首次需要）

**为什么不直接在 AI 配置里填密码？**
因为 Garmin 安全风控极严。异地/首次登录极大概率触发 Cloudflare 人机验证或 MFA 邮件验证码。如果把密码填在客户端的后台配置里，触发验证时 AI 助手会直接卡死，而你没有地方输入验证码。

因此本项目采用**两步走**：先在终端运行一次登录脚本，遇到验证码可以交互式输入。成功后 Token 缓存在本地，有效期约 1 年。

```bash
GARMIN_EMAIL="你的邮箱" GARMIN_PASSWORD="你的密码" garmin-mcp-lite-login
```

*(💡 **国内用户注意**：如果使用的是佳明中国区账号（garmin.cn），命令前加上 `GARMIN_IS_CN=true`。)*

Token 默认写入 `~/.garmin-mcp-lite/garmin_tokens.json`。需要多账号或多客户端隔离时，用 `GARMIN_TOKEN_DIR` 指定别的目录。

想一条命令引导完成？`garmin-mcp-lite-setup` 会依次检查两个登录 —— 先 Garmin，再（仅当你用小米秤时）Mi Fitness —— 缺什么就带你补什么。

### 3. 配置 AI 助手

#### Claude Desktop

在 `~/Library/Application Support/Claude/claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "garmin-lite": {
      "command": "/Users/you/.local/bin/garmin-mcp-lite",
      "args": []
    }
  }
}
```

想用 `uvx`？把 `command` 改成 `"uvx"`，`args` 改成 `["garmin-mcp-lite"]`。

#### Cursor / Windsurf / Gemini CLI

`command` 和 `args` 与上面完全一致。

#### Chatbox / opencode / 其他 GUI 客户端

Chatbox 这类客户端从 Finder 启动，**不继承** shell 的 `PATH`，直接写 `uvx` 会报 `spawn uvx ENOENT`。请填第 1 步装好的绝对路径。

**Chatbox**（设置 → MCP → 添加自定义）：

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/Users/you/.local/bin/garmin-mcp-lite",
      "args": []
    }
  }
}
```

**opencode**（`opencode.json`）格式不同：顶层是 `mcp`，必须写 `type`，`command` 是**数组**：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "garmin": {
      "type": "local",
      "command": ["/Users/you/.local/bin/garmin-mcp-lite"],
      "enabled": true,
      "timeout": 30000
    }
  }
}
```

> opencode 的 `timeout` 默认只有 5000ms。如果坚持用 `uvx`，务必调大。

### 环境变量

| 变量 | 默认值 | 作用 |
|:---|:---|:---|
| `GARMIN_IS_CN` | 未设置 | 中国区账号（garmin.cn）设为 `true`，必须与登录时使用的区域一致 |
| `GARMIN_TOKEN_DIR` | `~/.garmin-mcp-lite` | Token 存放目录，多账号时用来隔离 |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | 未设置 | 仅登录脚本使用，服务器本身不需要 |

### 常见问题

| 现象 | 原因 | 解决 |
|:---|:---|:---|
| `spawn uvx ENOENT`、`MCP error -32000: Connection closed` | 客户端在 `PATH` 里找不到 `uvx` | 改用已安装命令的绝对路径 |
| 一直连不上且无报错 | 首次下载依赖超过客户端超时 | 先 `uv tool install`，或调大 `timeout` |
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | 解析到了 `mcp` 2.x | `uv tool install --with "mcp<2" garmin-mcp-lite`，或升级到 ≥ 0.1.4 |
| 工具能列出但调用报 `Garmin token not found` | 本机没有缓存会话 | 运行 `garmin-mcp-lite-login` |
| garmin.cn 账号报认证失败 | 客户端环境缺少 `GARMIN_IS_CN` | 配置里加 `"env": {"GARMIN_IS_CN": "true"}` |
| 区间明显偏高，轻松跑落到 Z3 | 最大心率设得比真实值高 | 用 `garmin_zones` 核对，再去 Garmin Connect 修正最大心率 |

脱离客户端自检：

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | garmin-mcp-lite
```

正常情况下会返回 `serverInfo`（版本号为本包版本）和全部 19 个工具。

## 同步小米体脂秤

`garmin_sync_weight` 把小米运动健康（Mi Fitness）里的称重记录补进 Garmin，只写 Garmin 还没有的那几天。不需要定时任务，也不需要常驻进程：想起来调一次就行，隔了一周的数据一次就能补齐。

```bash
garmin-mcp-lite-xiaomi-login        # 只此一次：登录并报告云端有什么
```

登录要过图形验证码、可能要短信验证码，所以做不成工具调用。跑完它会打印记录数、时间范围、数据来源和最近五条 —— 如果显示 **0 条**，说明秤绑的是 Zepp Life，那套数据在另一个云、另一套 API，这个工具读不到。

然后直接问：

> 把小米秤的体重同步过来（先 dry run）

`dry_run=true` 只报告会写什么，不实际写。真正执行时，每一天都会以 FIT 体成分文件上传（与 Garmin Index 秤同一条通道），并回读当天记录确认写入成功。

几个值得知道的细节：

- **一天只取最早那次。** 早晨空腹体重才是趋势线要的东西，当天其余几次会被折叠并计数。
- **重复执行不会写重复。** Garmin 已有的天直接跳过，所以误触、重试都无害。
- **不合理的体重会被拒绝写入。** Garmin 的记录永不删除，所以写入前会先校验：窗口内已有 ≥3 条 Garmin 体重时，偏离中位数 ±40% 以上的直接跳过（斤恰好是千克的 2 倍，正中这条规则）；没有 Garmin 历史时，30–250 kg 之外的一律跳过。被拒的天会连同原因列出 —— 确属真实数据的话，用 `garmin_add_body_composition` 手动写入即可。
- **在小米侧删除记录不会同步删除 Garmin 的。** 本工具没有删除通道，多余记录请去 Garmin Connect App 手动删除。
- **写入之间有 0.5 秒间隔。** 首次补 90 天约 90 次上传，不加间隔会被 Garmin 用 429 拒绝（进而锁 IP 数小时）。
- **写入后无法回读验证会触发 `warning`。** 每次写入都会回读当天确认；如果反复出现不可验证，多半是运行本服务的机器与 Garmin 账号时区不一致，可能累积重复记录 —— 先对齐时区再继续同步。

小米 token 缓存在 `~/.garmin-mcp-lite/xiaomi.json`（权限 600），与 Garmin token 同目录。改密码、触发安全校验或长期不用都会让它失效，重新跑一次上面的命令即可。注意该 token 具备账号级权限，请当密码一样保管。

## 可以这样提问

连上之后，可以直接用自然语言问：

**训练**
- *"这周我的训练负荷分布怎么样？"*
- *"我六月的比赛目标是什么？按现在的状态预测能跑多少？"*
- *"拿我的全马 PB 和当前预测对比一下。"*

**健康**
- *"今天走了多少步？离目标还差多少？"*
- *"分析一下我昨晚的睡眠质量。"*
- *"我的跑步心率区间是多少？乳酸阈值落在哪个区？"*

**装备与目标**
- *"我的 Grossglockner 虚拟攀登进度如何？"*
- *"我的 Descent G1 固件是最新的吗？"*

## 开发者手动安装

如果你想修改源码：

```bash
git clone https://github.com/Golden0Voyager/garmin-mcp-lite.git
cd garmin-mcp-lite
uv sync

# 登录
GARMIN_EMAIL="your@email.com" GARMIN_PASSWORD="your_password" python -m garmin_mcp_lite.login

# 启动服务
python -m garmin_mcp_lite.server
```

提交 PR 前跑一遍与 CI 相同的检查：

```bash
uv run ruff check garmin_mcp_lite/ tests/ scripts/
uv run mypy garmin_mcp_lite/
uv run pytest --cov tests/
python3 scripts/smoke_wheel_install.py
```

当前语句覆盖率 100%，包含 `server.py` 里的 19 个工具注册表。
`tests/test_server.py` 把工具名逐个钉死了，改名或漏注册会直接测试失败，
而不是悄悄从客户端的 `tools/list` 里消失。

另有一个跑真实账号的端到端脚本，会把 19 个工具全部走一遍（需要先登录）：

```bash
python test_e2e.py
```

## 与原版对比

| | Taxuspt/garmin_mcp | garmin_mcp_lite |
|:---|:---|:---|
| 工具数量 | 80+ | 15 |
| 命名风格 | `mcp_garmin_get_activities_by_date` | `garmin_activities` |
| 聚合查询 | 无 | `fields` 参数控制详情粒度 |
| 成绩与纪录 | 无 | 成绩预测 + 个人纪录 |
| 心率区间 | 无 | 区间边界 + 乳酸阈值 + FTP |
| 健康深度 | 基础 | 血氧、呼吸、强度分钟、步数 |
| 写操作 | 大量（体重/营养/装备） | 仅读 |
| Schema 开销 | 高 | 19 个工具共约 2.4k tokens |

## 变更记录

### 0.1.8
- 新增 `garmin_status`：报告两个一次性登录（Garmin、小米）是否就位且有效，失效时给出
  要跑的确切命令。`ready` 只看 Garmin 侧 —— 没有小米秤的用户缺少小米 token 是正常配置。
- 新增 `garmin-mcp-lite-setup`：一条命令引导完成两个登录：先 Garmin（环境变量或交互输入），
  再一个可选、可跳过的 Mi Fitness 登录。
- 同步加固（`garmin_sync_weight`）：写入前校验体重的合理性（有 ≥3 条 Garmin 记录时，
  偏离中位数 ±40% 即拒绝 —— 斤恰好是千克的 2 倍；无历史时按 30–250 kg 绝对范围）；
  写入间隔 0.5 秒，首次 90 天回填不会触发 Garmin 限流；写入后无法回读验证时给出
  时区不一致警告；被跳过的天会附带原因。
- 小米客户端加固：分页超过 200 页即报错，不再被失控游标挂死；13 位毫秒时间戳自动折算为秒。
- 修复：`garmin_hr_trend` 原来逐天串行请求（90 天要等数分钟且极易触发限流），改为 6 路并行；
  `garmin_training_status` 的 7 天准备度扫描同样并行。
- 修复：`garmin_events` 文档承诺"即将到来"却返回整个日历（含已结束赛事），现在会过滤并按日期升序。
- 修复：`garmin_activity_detail` 的 `fields` 文档里列了从未实现的 `"gps"`，已移除。

### 0.1.7
- 新增 `garmin_body_composition`：体重/BMI/体脂率/肌肉量历史。Garmin 返回的质量单位是克，
  统一换算为千克，值为 null 的字段直接省略。
- 新增 `garmin_add_body_composition`：本项目第一个写入工具。以 FIT 体成分
  文件上传，与 Garmin Index 体脂秤走同一条通道。超过 500 千克的体重会被判定为误传克值并
  拒绝；当天已有记录时返回 `warning`。
- `test_e2e.py` 新增 `--write-test` 开关，写入验证需显式开启，日常端到端测试不碰账号数据。

- 新增 `garmin_sync_weight`：把小米体脂秤的称重记录同步进 Garmin，只补缺失的天。
  附带 `garmin_mcp_lite.xiaomi` —— 小米运动健康私有协议（RC4 + 双重 SHA1 签名，
  无公开文档）的只读客户端，在此重新实现，因此除 `requests` 外不引入新依赖；
  以及 `garmin-mcp-lite-xiaomi-login` 命令行入口，用于那一次无法绕开验证码的交互登录。
- `test_e2e.py` 中 `garmin_sync_weight` 默认以 dry_run 运行，未配置小米账号时自动跳过。

### 0.1.6
- 修复：`garmin_events` 在遇到没有自定义目标的赛事时报
  `'NoneType' object has no attribute 'get'` —— Garmin 返回的是
  `customGoal: null` 而不是省略这个 key，所以 `.get(key, {})` 的默认值永远不生效。
  真实日历里绝大多数赛事都是这种形状。
- 修复：`garmin_zones` 报 `'Garmin' object has no attribute
  'get_heart_rate_zones'`。该方法在 `garminconnect` 0.3.3（仍在支持范围内）里不存在；
  改为直接读 `/biometric-service/heartRateZones`，各版本通用。
- 修复：中间某个心率区间下限缺失时，下面的区间会一路延伸到最大心率，
  和上面所有区间重叠。
- 修复：Garmin 以 `null` 返回的嵌套对象（`summaryDTO`、`metadataDTO`、
  `dailySleepDTO`、`sleepScores`、`hrvSummary`、`userData`、`workoutSteps`、
  `acuteTrainingLoadDTO`、训练负荷平衡表）统一转成空容器，不再抛异常。
- 测试：语句覆盖率 90% → 100%（171 个用例）。`server.py` 不再从统计中排除，
  15 个工具注册表真正被断言。
- 测试：`tests/test_client.py` 不再 reload 客户端模块，所以 CI 里
  `-k 'not test_get_client'` 这个过滤条件被去掉了。
- 测试：`test_e2e.py` 覆盖全部 18 个工具（原来 9 个），单个工具失败不再中断后续检查。
- 重新打包：0.1.5 的 sdist 误打包了一个本地笔记文件。

### 0.1.5
- 新增 `garmin_race_prediction`：5K/10K/半马/全马成绩预测，支持 90 天与 1 年趋势。
- 新增 `garmin_personal_records`：个人纪录，附创造纪录的那次活动。
- 新增 `garmin_zones`：各运动心率区间边界、乳酸阈值、FTP。
- 修复：`serverInfo.version` 之前上报的是 `mcp` 依赖的版本，而非本包版本。
- 文档：补充 Chatbox / opencode 配置、常见问题表、环境变量。

### 0.1.4
- 限制 `mcp<2.0`，避免 `uvx` / `pip` 这类忽略锁文件的安装方式解析到 `mcp` 2.x。

## 许可证

[MIT](LICENSE) © 2026 Haining Yu

本项目基于第三方库 [garminconnect](https://github.com/cyberjunky/python-garminconnect)（MIT）封装，
非 Garmin 官方产品，使用前请遵守 Garmin Connect 服务条款。
