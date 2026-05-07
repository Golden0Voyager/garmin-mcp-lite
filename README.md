# Garmin MCP Lite

精简版 Garmin MCP 服务器，专为耐力运动爱好者设计。

## 核心工具（10个替代80+）

| 工具 | 功能 |
|:---|:---|
| `garmin_activities` | 查跑步/骑行/游泳/潜水记录，支持日期/类型筛选 |
| `garmin_activity_detail` | 单次活动详情（配速、心率、分段等） |
| `garmin_training_plan` | 今日/指定日期训练课表 |
| `garmin_training_status` | 训练状态、VO2Max、恢复时间、准备度 |
| `garmin_health` | 睡眠/HRV/压力/身体电量 |
| `garmin_gear` | 跑鞋/自行车装备库及里程 |
| `garmin_device` | 设备信息及同步状态 |
| `garmin_hr_trend` | 近 7/30/90 天静息心率趋势 |
| `garmin_weekly_stats` | 周/月/年训练总量统计 |
| `garmin_coach` | Garmin Coach 训练计划概览 |

## 安装

```bash
uv sync
```

## 配置

环境变量：
```bash
export GARMIN_EMAIL="your@email.com"
export GARMIN_PASSWORD="your_password"
```

首次请先登录并生成本地 token 缓存：
```bash
GARMIN_EMAIL="your@email.com" GARMIN_PASSWORD="your_password" \
python -m garmin_mcp_lite.login
```

之后启动 MCP 服务（自动复用 token）：
```bash
python -m garmin_mcp_lite.server
```

## Hermes 配置

在 `~/.hermes/config.yaml` 中添加：

```yaml
mcp_servers:
  garmin-lite:
    command: uv
    args:
      - run
      - --directory
      - /Users/hainingyu/Code/garmin_mcp_lite
      - python
      - -m
      - garmin_mcp_lite.server
```

## 与原版对比

| | Taxuspt/garmin_mcp | garmin_mcp_lite |
|:---|:---|:---|
| 工具数量 | 80+ | 10 |
| 命名风格 | `mcp_garmin_get_activities_by_date` | `garmin_activities` |
| 聚合查询 | 无 | `fields` 参数控制详情粒度 |
| 写操作 | 大量（体重/营养/装备） | 仅读（装备/体重由苹果健康同步） |
| 维护成本 | 依赖上游 | 自主可控 |
