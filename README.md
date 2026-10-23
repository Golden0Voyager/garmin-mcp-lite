# Garmin MCP Lite

<!-- AI CONTEXT START -->
> **[For AI Assistants & LLMs]** 
> You are interfacing with a Garmin MCP (Model Context Protocol) server. 
> 1. **Data Freshness**: Always query the data if the user asks about their recent workouts or health metrics.
> 2. **Parameter Tuning**: Use the `fields` parameter in tools like `garmin_activity_detail` to limit the response payload and save context window (e.g., `["splits", "hrZones"]`).
> 3. **Read-Only**: This server provides read-only access to Garmin Connect. You cannot modify user data.
> 4. **No Password Request**: Never ask the user for their Garmin password. Authentication is handled out-of-band via a local token.
> 5. **Health Tip**: `garmin_health` now supports a `metric` parameter — use `"steps"`, `"sleep"`, `"hrv"`, `"spo2"`, `"body_battery"`, etc., to query specific data and save context window.
> 6. **Zone Context**: `garmin_activity_detail` returns seconds per heart rate zone but no boundaries. Call `garmin_zones` first to get the bpm ranges before judging intensity.
<!-- AI CONTEXT END -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/garmin-mcp-lite.svg)](https://badge.fury.io/py/garmin-mcp-lite)

*Read this in other languages: [English](README.md), [简体中文](README.zh-CN.md).*

A lightweight Garmin Model Context Protocol (MCP) server, designed specifically for endurance athletes.

It exposes **15 precisely-curated endpoints** for deep analysis of running, cycling, swimming, and health data — replacing bulky 80+ endpoint alternatives with a clean, focused toolset.

## Core Tools (15)

### 🏃 Activity & Training

| Tool | Functionality |
|:---|:---|
| `garmin_activities` | List running/cycling/swimming/diving records with date & type filters. |
| `garmin_activity_detail` | Get single activity details (pace, heart rate zones, splits, GPS, etc.). |
| `garmin_training_plan` | Get today's or a specific date's scheduled training workout. |
| `garmin_training_status` | Get training status, VO2Max, **acute load**, **load focus distribution** (aerobic/anaerobic), recovery time, and training readiness score. |
| `garmin_weekly_stats` | Get weekly/monthly/yearly training volume statistics. |
| `garmin_coach` | Overview of current Garmin Coach training plans. |
| `garmin_race_prediction` | Predicted 5K/10K/half/marathon finish times with pace, plus the change over a 90-day or 1-year window. |
| `garmin_personal_records` | Personal bests (1K → marathon, longest run/ride, swim times, step records) with the activity that set each one. |

### 💚 Health & Wellness

| Tool | Functionality |
|:---|:---|
| `garmin_health` | Get comprehensive health metrics: sleep quality, HRV status, stress, body battery, **SpO2**, **respiration rate**, **intensity minutes**, **daily steps**, **floors climbed**, and resting heart rate. Supports `metric` parameter for targeted queries. |
| `garmin_hr_trend` | Get resting heart rate trends for the last 7/30/90 days. |
| `garmin_zones` | Heart rate zone boundaries (bpm ranges) per sport, plus lactate threshold and FTP. Use it to interpret the `hrZones` durations returned by `garmin_activity_detail`. |

### 🎯 Goals & Challenges

| Tool | Functionality |
|:---|:---|
| `garmin_events` | Get your race calendar: upcoming race dates, target distances, and **goal finish times**. |
| `garmin_challenges` | Get in-progress challenges: virtual climbs, monthly badge challenges, and their completion percentages. |

### ⌚ Device & Gear

| Tool | Functionality |
|:---|:---|
| `garmin_gear` | Get your shoe/bike gear list and their **real cumulative mileage**. |
| `garmin_device` | Get connected device info: firmware version, **update availability**, primary device status, and registration date. |

## Quickstart

There are two ways to run the server. **Installing it as a command is the safer default** — it starts in well under a second, needs no network at launch, and GUI clients can find it. `uvx` works too, but it downloads on first run and is invisible to clients that do not inherit your shell `PATH`.

### 1. Install

```bash
uv tool install garmin-mcp-lite
which garmin-mcp-lite     # → ~/.local/bin/garmin-mcp-lite
```

<details>
<summary>Alternative: run via <code>uvx</code> without installing</summary>

```bash
uvx garmin-mcp-lite
```

Fine for terminal clients such as Claude Code or Codex CLI. See [Troubleshooting](#troubleshooting) for why GUI clients usually need the installed path instead.
</details>

### 2. Authenticate (First Time Only)

**Why not just put the password in the AI config?**
Garmin has strict security measures. Logging in from a new location/MCP server often triggers Cloudflare CAPTCHAs or MFA email codes. If the password sits in a client's background config, the AI assistant silently freezes when challenged, with no way for you to type the code in.

So this project uses a **two-step strategy**: run the login script in your terminal first. If Garmin challenges you, you can type the MFA code interactively. On success the session token is cached locally and stays valid for roughly a year.

```bash
GARMIN_EMAIL="your@email.com" GARMIN_PASSWORD="your_password" garmin-mcp-lite-login
```

*(💡 **China Region Users**: if your account is registered with Garmin China (garmin.cn), prefix the command with `GARMIN_IS_CN=true`.)*

The token is written to `~/.garmin-mcp-lite/garmin_tokens.json`. Set `GARMIN_TOKEN_DIR` to keep several clients or accounts on separate sessions.

### 3. Configure Your AI Assistant

#### Claude Desktop

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Prefer `uvx`? Use `"command": "uvx"` with `"args": ["garmin-mcp-lite"]`.

#### Cursor / Windsurf / Gemini CLI

Use the same `command` and `args` as above.

#### Chatbox / opencode / Other GUI Clients

GUI clients such as Chatbox are launched from Finder and do **not** inherit your shell `PATH`, so a bare `uvx` fails with `spawn uvx ENOENT`. Point them at the absolute path from step 1.

**Chatbox** (Settings → MCP → Add custom):

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

**opencode** (`opencode.json`) uses a different schema — the key is `mcp`, `type` is required, and `command` is an array:

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

> opencode's `timeout` defaults to 5000 ms. Raise it if you insist on `uvx` instead of an installed command.

### Environment Variables

| Variable | Default | Purpose |
|:---|:---|:---|
| `GARMIN_IS_CN` | unset | Set to `true` for accounts registered with Garmin China (garmin.cn). Must match the region used at login. |
| `GARMIN_TOKEN_DIR` | `~/.garmin-mcp-lite` | Where the session token lives. Change it to isolate multiple accounts. |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | unset | Login script only. Never needed by the server itself. |

### Troubleshooting

| Symptom | Cause | Fix |
|:---|:---|:---|
| `spawn uvx ENOENT`, `MCP error -32000: Connection closed` | client cannot find `uvx` on `PATH` | use the absolute path of the installed command |
| Server never connects, no error shown | first-run download exceeded the client timeout | `uv tool install` first, or raise `timeout` |
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | `mcp` 2.x was resolved by a lock-ignoring install | `uv tool install --with "mcp<2" garmin-mcp-lite`, or upgrade to ≥ 0.1.4 |
| Tools list loads, calls fail with `Garmin token not found` | no cached session on this machine | run `garmin-mcp-lite-login` |
| `Authentication failed` on a garmin.cn account | `GARMIN_IS_CN` missing from the client's env | add `"env": {"GARMIN_IS_CN": "true"}` |
| Zones look too high, "easy" runs land in Z3 | max heart rate set above your real one | check `garmin_zones`, then fix MaxHR in Garmin Connect |

Verify the server independently of any client:

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | garmin-mcp-lite
```

Expect a `serverInfo` line reporting this package's version, followed by all 15 tools.

## Example Queries

Once connected, you can ask your AI assistant natural-language questions like:

**Training**
- *"What's my training load focus this week?"*
- *"Show me my race goal for June and what my current predicted finish time is."*
- *"Compare my marathon PB against the current prediction."*

**Health**
- *"How many steps have I taken today? Am I on track for my daily goal?"*
- *"Analyze my sleep quality from last night."*
- *"What are my heart rate zones for running, and where does my lactate threshold sit?"*

**Gear & Goals**
- *"How's my Grossglockner virtual climb challenge going?"*
- *"Is my Descent G1 firmware up to date?"*

## Manual Installation (for Developers)

If you want to modify the code:

```bash
git clone https://github.com/Golden0Voyager/garmin-mcp-lite.git
cd garmin-mcp-lite
uv sync

# Login
GARMIN_EMAIL="your@email.com" GARMIN_PASSWORD="your_password" python -m garmin_mcp_lite.login

# Run server
python -m garmin_mcp_lite.server
```

Run the same gates CI runs before opening a PR:

```bash
uv run ruff check garmin_mcp_lite/ tests/ scripts/
uv run mypy garmin_mcp_lite/
uv run pytest --cov -k 'not test_get_client' tests/
python3 scripts/smoke_wheel_install.py
```

## Comparison with Other Garmin MCPs

| | Taxuspt/garmin_mcp | garmin_mcp_lite |
|:---|:---|:---|
| Tool Count | 80+ | 15 |
| Naming | `mcp_garmin_get_activities_by_date` | `garmin_activities` |
| Deep Queries | No | `fields` parameter controls detail granularity |
| Training Load | Basic | Acute load + load focus distribution |
| Performance | No | Race predictions + personal records |
| Zones | No | HR zone boundaries + lactate threshold + FTP |
| Health Depth | Basic | SpO2, respiration, intensity minutes, steps |
| Race/Challenge | No | Events calendar + challenge progress |
| Write Ops | Heavy (weight/nutrition/gear) | Read-only |
| Schema cost | High | ~2.3k tokens for all 15 tools |

## Changelog

### 0.1.6
- Repackage only: the 0.1.5 sdist accidentally shipped a local notes file. No code changes.

### 0.1.5
- New: `garmin_race_prediction` — predicted 5K/10K/half/marathon times, with 90-day and 1-year trends.
- New: `garmin_personal_records` — personal bests with the activity that set each one.
- New: `garmin_zones` — per-sport heart rate zone boundaries, lactate threshold, and FTP.
- Fix: `serverInfo.version` reported the `mcp` dependency's version instead of this package's.
- Docs: client setup for Chatbox and opencode, troubleshooting table, environment variables.

### 0.1.4
- Cap `mcp<2.0` so lock-ignoring installers (`uvx`, `pip`) stop resolving `mcp` 2.x.

## License

[MIT](LICENSE) © 2026 Haining Yu

This project is built on top of the excellent [garminconnect](https://github.com/cyberjunky/python-garminconnect) library. It is not an official Garmin product. Please adhere to Garmin Connect's terms of service when using this tool.
