# Garmin MCP Lite

<!-- AI CONTEXT START -->
> **[For AI Assistants & LLMs]** 
> You are interfacing with a Garmin MCP (Model Context Protocol) server. 
> 1. **Data Freshness**: Always query the data if the user asks about their recent workouts or health metrics.
> 2. **Parameter Tuning**: Use the `fields` parameter in tools like `garmin_activity_detail` to limit the response payload and save context window (e.g., `["splits", "hrZones"]`).
> 3. **Read-Only**: This server provides read-only access to Garmin Connect. You cannot modify user data.
> 4. **No Password Request**: Never ask the user for their Garmin password. Authentication is handled out-of-band via a local token.
> 5. **Health Tip**: `garmin_health` now supports a `metric` parameter — use `"steps"`, `"sleep"`, `"hrv"`, `"spo2"`, `"body_battery"`, etc., to query specific data and save context window.
<!-- AI CONTEXT END -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/garmin-mcp-lite.svg)](https://badge.fury.io/py/garmin-mcp-lite)

*Read this in other languages: [English](README.md), [简体中文](README.zh-CN.md).*

A lightweight Garmin Model Context Protocol (MCP) server, designed specifically for endurance athletes. 

It exposes **12 precisely-curated endpoints** for deep analysis of running, cycling, swimming, and health data — replacing bulky 80+ endpoint alternatives with a clean, focused toolset.

## Core Tools (12)

### 🏃 Activity & Training

| Tool | Functionality |
|:---|:---|
| `garmin_activities` | List running/cycling/swimming/diving records with date & type filters. |
| `garmin_activity_detail` | Get single activity details (pace, heart rate zones, splits, GPS, etc.). |
| `garmin_training_plan` | Get today's or a specific date's scheduled training workout. |
| `garmin_training_status` | Get training status, VO2Max, **acute load**, **load focus distribution** (aerobic/anaerobic), recovery time, and training readiness score. |
| `garmin_weekly_stats` | Get weekly/monthly/yearly training volume statistics. |
| `garmin_coach` | Overview of current Garmin Coach training plans. |

### 💚 Health & Wellness

| Tool | Functionality |
|:---|:---|
| `garmin_health` | Get comprehensive health metrics: sleep quality, HRV status, stress, body battery, **SpO2**, **respiration rate**, **intensity minutes**, **daily steps**, **floors climbed**, and resting heart rate. Supports `metric` parameter for targeted queries. |
| `garmin_hr_trend` | Get resting heart rate trends for the last 7/30/90 days. |

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

## Quickstart (via PyPI & uv)

The easiest way to run this server is using `uvx` (no cloning required).

### 1. Authenticate (First Time Only)

**Why not just put the password in the AI config?**
Garmin has strict security measures. Logging in from a new location/MCP server often triggers Cloudflare CAPTCHAs or MFA email codes. If the password is in Claude's background config, the AI assistant will silently freeze or fail when challenged, with no way for you to input the code.

Therefore, this plugin uses a secure **two-step strategy**: Run a login script in your terminal first. If challenged, you can interactively input the MFA code. Upon success, a session token is cached locally (valid for ~1 year).

```bash
GARMIN_EMAIL="your@email.com" GARMIN_PASSWORD="your_password" uvx --with garmin-mcp-lite garmin-mcp-lite-login
```
*(💡 **China Region Users**: If your account is registered in Garmin China (garmin.cn), prefix the command with `GARMIN_IS_CN=true`.)*

### 2. Configure Your AI Assistant

Once authenticated, add the server to your favorite MCP-compatible AI assistant.

#### Claude Desktop

Add this to your `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "garmin-lite": {
      "command": "uvx",
      "args": [
        "garmin-mcp-lite"
      ]
    }
  }
}
```

#### Cursor / Windsurf / Gemini CLI / Other MCP Clients

Use the exact same `command` and `args` as above. The server will automatically load the cached token from `~/.garmin-mcp-lite/garmin_tokens.json`.

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

## Example Queries

Once connected, you can ask your AI assistant natural-language questions like:

- *"What's my training load focus this week?"*
- *"Show me my race goal for June and what my current predicted finish time is."*
- *"How's my Grossglockner virtual climb challenge going?"*
- *"Is my Descent G1 firmware up to date?"*
- *"How many steps have I taken today? Am I on track for my daily goal?"*
- *"Analyze my sleep quality from last night."*

## Comparison with Other Garmin MCPs

| | Taxuspt/garmin_mcp | garmin_mcp_lite |
|:---|:---|:---|
| Tool Count | 80+ | 12 |
| Naming | `mcp_garmin_get_activities_by_date` | `garmin_activities` |
| Deep Queries | No | `fields` parameter controls detail granularity |
| Training Load | Basic | Acute load + load focus distribution |
| Health Depth | Basic | SpO2, respiration, intensity minutes, steps |
| Race/Challenge | No | Events calendar + challenge progress |
| Write Ops | Heavy (weight/nutrition/gear) | Read-only |

## License

[MIT](LICENSE) © 2026 Haining Yu

This project is built on top of the excellent [garminconnect](https://github.com/cyberjunky/python-garminconnect) library. It is not an official Garmin product. Please adhere to Garmin Connect's terms of service when using this tool.
