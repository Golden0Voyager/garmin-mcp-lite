# Garmin MCP Lite

<!-- AI CONTEXT START -->
> **[写给 AI 助手与 LLM]** 
> 你当前正在连接一个 Garmin MCP (Model Context Protocol) 服务器。
> 1. **数据新鲜度**：当用户询问其最近的运动或健康指标时，务必主动调用接口获取最新数据，不要使用陈旧上下文。
> 2. **参数调优**：在调用 `garmin_activity_detail` 等工具时，使用 `fields` 参数来限制返回的载荷大小，以节省上下文窗口（例如：`["splits", "hrZones"]`）。
> 3. **只读权限**：此服务器仅提供对 Garmin Connect 的只读访问权限。你无法修改或写入用户的任何数据。
> 4. **禁止索要密码**：绝对不要向用户索要他们的 Garmin 密码。身份验证已在外部通过本地 Token 安全完成。
> 5. **区间解读**：`garmin_activity_detail` 返回的心率区间只有秒数、没有边界。判断强度前先调用 `garmin_zones` 拿到各区间 bpm 范围。
<!-- AI CONTEXT END -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/garmin-mcp-lite.svg)](https://badge.fury.io/py/garmin-mcp-lite)

*Read this in other languages: [English](README.md), [简体中文](README.zh-CN.md).*

精简版 Garmin MCP 服务器，专为耐力运动爱好者设计。

提取了进行深度运动数据分析最核心的 15 个接口（涵盖跑步、骑行、游泳及健康数据），完美替代臃肿的 80+ 接口方案。

## 核心工具（15 个替代 80+）

### 🏃 活动与训练

| 工具 | 功能 |
|:---|:---|
| `garmin_activities` | 查跑步/骑行/游泳/潜水记录，支持日期/类型筛选 |
| `garmin_activity_detail` | 单次活动详情（配速、心率区间、分段、GPS 等） |
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

### 🎯 目标与挑战

| 工具 | 功能 |
|:---|:---|
| `garmin_events` | 赛事日历：比赛日期、目标距离、目标完赛时间 |
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

正常情况下会返回 `serverInfo`（版本号为本包版本）和全部 15 个工具。

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
uv run pytest --cov -k 'not test_get_client' tests/
python3 scripts/smoke_wheel_install.py
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
| Schema 开销 | 高 | 15 个工具共约 2.3k tokens |

## 变更记录

### 0.1.6
- 仅重新打包：0.1.5 的 sdist 误打包了一个本地笔记文件，代码无改动。

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
