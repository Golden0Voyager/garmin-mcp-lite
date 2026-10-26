# Garmin MCP Lite

<!-- AI CONTEXT START -->
> **[For AI Assistants & LLMs]** 
> You are interfacing with a Garmin MCP (Model Context Protocol) server. 
> 1. **Data Freshness**: Always query the data if the user asks about their recent workouts or health metrics.
> 2. **Parameter Tuning**: Use the `fields` parameter in tools like `garmin_activity_detail` to limit the response payload and save context window (e.g., `["splits", "hrZones"]`).
> 3. **Mostly Read-Only**: 17 tools read. Three write weight data (`garmin_add_body_composition`, `garmin_sync_weight`, `garmin_sync_healthkit`): confirm the numbers with the user before calling, and prefer `dry_run=true` for the syncs — there is no undo.
> 4. **No Password Request**: Never ask the user for their Garmin password. Authentication is handled out-of-band via a local token.
> 5. **Health Tip**: `garmin_health` now supports a `metric` parameter — use `"steps"`, `"sleep"`, `"hrv"`, `"spo2"`, `"body_battery"`, etc., to query specific data and save context window.
> 6. **Zone Context**: `garmin_activity_detail` returns seconds per heart rate zone but no boundaries. Call `garmin_zones` first to get the bpm ranges before judging intensity.
> 7. **Setup Check**: `garmin_status` reports whether the one-time logins (Garmin required, Mi Fitness optional) are valid and, when not, the exact command to run next. Call it before troubleshooting anything auth-related.
<!-- AI CONTEXT END -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/garmin-mcp-lite.svg)](https://badge.fury.io/py/garmin-mcp-lite)

*Read this in other languages: [English](README.md), [简体中文](README.zh-CN.md).*

A lightweight Garmin Model Context Protocol (MCP) server, designed specifically for endurance athletes.

It exposes **20 precisely-curated endpoints** for deep analysis of running, cycling, swimming, and health data — replacing bulky 80+ endpoint alternatives with a clean, focused toolset.

17 of them read. Three write: `garmin_add_body_composition` for a single manual weigh-in, `garmin_sync_weight` to pull them from a Xiaomi body-fat scale, and `garmin_sync_healthkit` for scales whose apps write to Apple Health — Garmin has no way to accept weight data from a third-party scale.

## Core Tools (20)

### 🔧 Setup & Diagnosis

| Tool | Functionality |
|:---|:---|
| `garmin_status` | Check both one-time logins (Garmin required, Mi Fitness optional) and report the exact command to run next when something is missing or expired. |

### 🏃 Activity & Training

| Tool | Functionality |
|:---|:---|
| `garmin_activities` | List running/cycling/swimming/diving records with date & type filters. |
| `garmin_activity_detail` | Get single activity details (pace, heart rate zones, splits, laps). |
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

### ⚖️ Body Composition

| Tool | Functionality |
|:---|:---|
| `garmin_body_composition` | Weight and body-composition history: weight, BMI, body fat %, body water %, muscle mass, bone mass, visceral fat, metabolic age. Mass is normalised to kilograms and unmeasured fields are omitted. |
| `garmin_add_body_composition` | **Write** one measurement (weight required, everything else optional). Uploads a FIT body-composition file — the same channel Garmin's own Index scale uses. |
| `garmin_sync_weight` | **Write** weigh-ins from a Xiaomi body-fat scale into Garmin. Only days Garmin does not already have are written, so it is idempotent. Needs a one-time `garmin-mcp-lite-xiaomi-login`. |
| `garmin_sync_healthkit` | **Write** weigh-ins that an iPhone Shortcut mirrored from Apple Health into Garmin — for scales whose app (蚂蚁阿福, etc.) has no cloud this server can read. Same idempotent, plausibility-checked write path. See [Apple Health bridge](#syncing-a-xiaomi-body-fat-scale). |

> **`garmin_add_body_composition` writes to your Garmin account.** There is no undo through this tool. Garmin keeps every entry, so calling it twice for the same day can leave two weigh-ins; the response warns you when that day already had one. `weight` is in **kilograms** — values above 500 are rejected as an accidental gram value, because the read tool returns grams at the API level and a read-modify-write is the obvious way to get this wrong. Garmin's upload endpoint does not always report a status, so the tool reads the day back and returns `verified: true` only when the stored weight matches what it sent.

### 🎯 Goals & Challenges

| Tool | Functionality |
|:---|:---|
| `garmin_events` | Get your upcoming race calendar: race dates (soonest first, past events excluded), target distances, and **goal finish times**. |
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

Prefer one guided command? `garmin-mcp-lite-setup` checks both logins — Garmin, and (only if you use a Xiaomi scale) Mi Fitness — and walks you through whatever is missing.

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
| `GARMIN_HEALTH_FILE` | iCloud Drive `garmin/weight.txt` | The file the Apple Health bridge Shortcut appends to. |
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

Expect a `serverInfo` line reporting this package's version, followed by all 20 tools.

## Syncing a Xiaomi Body-Fat Scale

`garmin_sync_weight` copies weigh-ins from Mi Fitness (小米运动健康) into Garmin, filling only the days Garmin does not already have. There is no scheduler and nothing to keep running: call it when you feel like it, and a week of missed days catches up in one go.

```bash
garmin-mcp-lite-xiaomi-login        # once: logs in and reports what the cloud holds
```

Logging in needs a captcha and possibly an SMS code, so it cannot be a tool call. Afterwards it prints the record count, the date range, the data source and the last five entries — if that says **0 records**, the scale is bound to Zepp Life instead, whose data lives in a different cloud with a different API, and this tool cannot read it.

Then ask your assistant:

> sync my weight from the Xiaomi scale (dry run first)

`dry_run=true` reports what would be written and writes nothing. Real runs write each day as a FIT body-composition file, the same channel a Garmin Index scale uses, and confirm each one by reading the day back.

Details worth knowing:

- **Only the earliest weigh-in of a day is used.** Morning, fasted weight is the one a trend line is about; later ones are reported as collapsed.
- **A re-run writes nothing.** Days Garmin already has are skipped, so a repeat call after a crash or a double-click is harmless.
- **Implausible weights are refused.** Garmin keeps every entry forever, so before writing, each weight is checked: with ≥3 Garmin weigh-ins inside the window, anything more than ±40% off their median is skipped (a 斤 mis-read is exactly 2× kg); without Garmin history, weights outside 30–250 kg are skipped. Refusals are listed with the reason — write one deliberately with `garmin_add_body_composition` if it was genuine.
- **Deleting a weigh-in in Mi Fitness does not delete it from Garmin.** There is no delete path here; remove stray entries in the Garmin Connect app.
- **Writes are paced 0.5 s apart.** A first 90-day backfill is ~90 uploads; without the pause Garmin answers the burst with a 429 (which then locks the IP for hours).
- **A `warning` about unverifiable writes means timezone trouble.** Each write is confirmed by reading the day back; if writes keep coming back unverifiable, the machine running this server likely has a different timezone than the Garmin account, and duplicates may accumulate — align the timezones before syncing again.

The Xiaomi token is cached at `~/.garmin-mcp-lite/xiaomi.json` (mode 600), next to the Garmin token. It expires when you change your Xiaomi password or trigger a security check — re-run the login command when that happens. Note that the token grants account-level access, so treat the file like a password.

### Bridging other scales via Apple Health

The Xiaomi sync reads Mi Fitness only. If your scale's app can write to Apple Health — Withings, Huawei Health, Yunmai, Renpho and most mainstream scales do — an iPhone Shortcut becomes the bridge: Health data is mirrored into a file in iCloud Drive, and `garmin_sync_healthkit` reads that file on your Mac and fills Garmin's gaps with the same idempotent, plausibility-checked write path. It depends on no vendor cloud; weight typed manually into the Health app works too.

The steps below come from a complete real-world setup — every pitfall listed was hit for real.

#### Step 0: Confirm your scale's app actually writes to Apple Health

Do this check **before** configuring anything:

1. Weigh in, wait a minute, open Health → Browse → Weight, and check whether the newest entry's source is your scale's app.
2. Or: Settings → Health → Data Access & Devices → your scale's app. If there is only an "Allow Reading" list and **no "Allow Writing" section at all, the app has never requested write access and this bridge cannot work** (real-world example: the Ant Afu app — no sync switch inside the app, no write section in Health; a dead end).

#### Step 1: Prepare the bridge file

Create a `garmin` folder with a `weight.txt` file in iCloud Drive. Two pitfalls, both hit in practice:

- **The extension must be `.txt`.** Shortcuts' "Append to Text File" picker only enables recognized text types — a `.jsonl` file shows up greyed out. The content is unchanged (one JSON object per line); the tool does not care about the extension, but the iPhone's file picker does.
- **A 0-byte file does not trigger iCloud sync**, so the phone may not see it. Write one line into the file from the Mac and wait half a minute; in the Files app on the iPhone, pull down to refresh under Browse → iCloud Drive.

#### Step 2: Create the shortcut (e.g. "Weigh-in bridge")

Add actions one by one from the **search box at the bottom**; each new action connects below the last. Six actions, in order:

| # | Action | Required settings (defaults are wrong — check each) |
|---|--------|------|
| 1 | Find Health Samples | Type: `Weight`; **Unit: Kilograms** (pins the value to kg regardless of the Health app's display unit); Sort By: `Start Date`, Order: `Newest First`; **Limit: on, Get 1 item** |
| 2 | Get Details of Health Sample | Input: the sample; Detail: **Value** (without this the variable carries the "kg" unit text) |
| 3 | Get Details of Health Sample | Same sample; Detail: **Start Date** |
| 4 | Format Date | Date Format: Custom, `yyyy-MM-dd'T'HH:mm:ss`. **Use the sample's date, not "Current Date"** — a delayed trigger still records the real measurement time |
| 5 | Text | See template below. Insert variables from the **variable bar above the keyboard**, do not type them; **press Return once after the `}`** — "Append to Text File" adds no trailing newline, and skipping this glues the next record onto the same line |
| 6 | Append to Text File | File: iCloud Drive → `garmin` → `weight.txt` |

Content of the Text action (brackets = insert the matching variable):

```
{"timestamp": [formatted date], "weight_kg": [value]}
```

If your scale also writes body fat / BMI, add one more "Find Health Samples + Get Details · Value" pair per metric (Type: `Body Fat Percentage` / `BMI`, settings as in step 1) and extend the text with `,"body_fat_pct": [fat value]`. **Include only metrics your scale actually writes**: a variable that comes back empty glues the line into a broken one and the weight is lost too. Note Health's standard types are only weight, body fat percentage and BMI — extended metrics a scale app displays (muscle mass, bone mass, visceral fat) never reach Health and cannot cross this bridge.

#### Step 3: Run it once manually

Tap **▶** at the bottom right. The first run asks for Health and Files permissions — allow both. The Text card should show something like `{"timestamp": "2026-10-25T09:08:00", "weight_kg": 72.2}`; `cat` the weight.txt on the Mac to confirm.

#### Step 4: Set up the automation (verified on iOS 17/18)

1. Shortcuts app → **Automation** tab → **+** → pick **App** in the trigger list
2. Choose **Close**, pick your scale's app, **turn off "Ask Before Running"**
3. Tap **Done** at the top right — there is no "Next" button
4. Back in the Automation list, **open the newly created card** and pick the shortcut from the card's empty slot; if search fails, try a short keyword
5. Leave the card's "Input / Select Variable" field **empty** — the shortcut fetches the data from Health itself

Skipping the automation is fine: tapping the shortcut from the widget after a weigh-in works identically.

#### Step 5: Sync

Ask your assistant to run `garmin_sync_healthkit` (dry run first). The default file is `~/Library/Mobile Documents/com~apple~CloudDocs/garmin/weight.txt`; set `GARMIN_HEALTH_FILE` to point somewhere else.

#### Troubleshooting (all of these really happened)

| Symptom | Cause | Fix |
|:---|:---|:---|
| File greyed out in "Append to Text File" | iOS picker does not recognize `.jsonl` and friends | Use a `.txt` extension |
| The garmin folder never shows up on the phone | A 0-byte file does not trigger iCloud sync | Write a line into the file from the Mac; pull-to-refresh in Files |
| Conflict copies like `weight.txt.json` appear | The shortcut appended to a different file the iPhone created itself | Delete the copies **on the iPhone** and re-point the shortcut at weight.txt (deleting only on the Mac gets overwritten again) |
| The same line appears several times | Automation fired repeatedly, or manual + automation both ran | Harmless — the tool deduplicates by timestamp |
| `unparsed` > 0 in the sync result | Missing trailing newline in the Text action glued two records together | The tool splits glued JSON objects automatically; still, add the newline |
| A weigh-in never shows up | The scale app has not written it to Health yet | Back to Step 0: check the source in the Health app |

The file is append-only and this tool never edits it: repeated lines, re-runs and double triggers are all harmless (duplicates collapse by timestamp, days collapse to the earliest weigh-in, days Garmin already has are skipped). Even if the Health app displays 斤 on your phone: the shortcut pins kilograms, and the plausibility gate would refuse a 2× value before it reaches Garmin.

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
uv run pytest --cov tests/
python3 scripts/smoke_wheel_install.py
```

The suite is at 100% statement coverage across every module, including the
20-tool registry in `server.py`. `tests/test_server.py` pins the exact tool
names, so a rename or a dropped `add_tool()` call fails a test instead of
silently disappearing from a client's `tools/list`.

There is also a live end-to-end script that walks all 20 tools against your own
account (needs a login token):

```bash
python test_e2e.py
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
| Schema cost | High | ~2.5k tokens for all 20 tools |

## Changelog

### 0.1.8
- New: `garmin_sync_healthkit` — copies weigh-ins that an iPhone Shortcut mirrored
  from Apple Health (one JSON line per measurement in an iCloud Drive file) into
  Garmin. Built for scales whose app has no readable cloud, such as 蚂蚁阿福.
  Shares the Xiaomi sync's per-day dedup, plausibility gate, paced writes and
  read-back verification; the bridge file is append-only and never edited by the
  tool, so re-runs and double triggers are harmless.

### 0.1.7
- New: `garmin_body_composition` — weight/BMI/body-fat/muscle-mass history. Garmin
  returns mass in grams; it is normalised to kilograms and null fields are dropped.
- New: `garmin_add_body_composition` — the first (and only) write tool. Uploads a FIT
  body-composition file, the same channel the Garmin Index scale uses. Weights above
  500 kg are rejected as an accidental gram value, and the response warns when the
  day already had an entry.
- New: `garmin_sync_weight` — pulls weigh-ins from a Xiaomi body-fat scale into Garmin.
  Only days Garmin lacks are written, so it is idempotent. Adds
  `garmin_mcp_lite.xiaomi`, a read-only client for Mi Fitness's private RC4/SHA1-signed
  protocol (undocumented; reimplemented here so nothing beyond `requests` is needed),
  and the `garmin-mcp-lite-xiaomi-login` console script for the one-time interactive
  login that a captcha makes unavoidable.
- New: `garmin_status` — reports whether the one-time logins (Garmin, Mi Fitness)
  are in place and still valid, and names the exact command to run next. `ready`
  reflects the Garmin side only: a missing Xiaomi token is a valid configuration
  for anyone without the scale.
- New: `garmin-mcp-lite-setup` — one guided command for both logins: Garmin first
  (env vars or interactive prompt), then an optional, skippable Mi Fitness login.
- Sync hardening (`garmin_sync_weight`): implausible weights are refused before
  writing (±40% off the recent Garmin median with ≥3 points — a 斤 mis-read is
  exactly 2× kg — otherwise the 30–250 kg band); writes are paced 0.5 s apart so
  a 90-day backfill cannot trip Garmin's rate limiter; a written-but-unverifiable
  day raises a timezone-mismatch warning; skipped days carry their reason.
- Mi client hardening: pagination stops after 200 pages instead of hanging on a
  runaway cursor; 13-digit (millisecond) timestamps are scaled to seconds.
- Fix: `garmin_hr_trend` fetched its window one serial request per day — a 90-day
  call was minutes of waiting and rate-limit bait; days are now fetched six at a
  time. `garmin_training_status` scans its 7 readiness days in parallel too.
- Fix: `garmin_events` promised "upcoming" but returned the whole calendar, past
  events included; it now drops them and sorts soonest first.
- Fix: `garmin_activity_detail` documented a "gps" value for `fields` that never
  existed; the docstring no longer suggests it.
- `test_e2e.py` grew a `--write-test` flag; the write path is opt-in so a routine
  end-to-end run never touches account data. `garmin_sync_weight` runs in `dry_run`
  mode by default there, skips when no Xiaomi account is configured, and the run
  now opens with a `garmin_status` step.

### 0.1.6
- Fix: `garmin_events` crashed with `'NoneType' object has no attribute 'get'` on any
  event without a custom goal — Garmin sends `customGoal: null` rather than omitting
  the key, so `.get(key, {})` never applied. Affected most real calendars.
- Fix: `garmin_zones` crashed with `'Garmin' object has no attribute
  'get_heart_rate_zones'`. That method is absent in `garminconnect` 0.3.3 (still
  within the supported range); the tool now reads
  `/biometric-service/heartRateZones` directly, which is stable across versions.
- Fix: a missing intermediate zone floor no longer makes the zone below it extend
  all the way to max HR and overlap every zone above it.
- Fix: nested payloads that Garmin sends as `null` (`summaryDTO`, `metadataDTO`,
  `dailySleepDTO`, `sleepScores`, `hrvSummary`, `userData`, `workoutSteps`,
  `acuteTrainingLoadDTO`, training load balance map) are now coerced to empty
  containers instead of raising.
- Test: statement coverage 90% → 100% (171 tests). `server.py` is measured now
  instead of omitted, so the 15 tool registrations are actually asserted.
- Test: `tests/test_client.py` no longer reloads the client module, which is why
  CI had to skip it with `-k 'not test_get_client'`; that filter is gone.
- Test: `test_e2e.py` covers all 18 tools (was 9) and keeps going after a failure
  so one broken tool does not hide the rest.
- Repackage: the 0.1.5 sdist accidentally shipped a local notes file.

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
