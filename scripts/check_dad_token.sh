#!/usr/bin/env bash
# 老愚(爸爸)健康管家的 Garmin 账号隔离守卫 —— 只告警，绝不改配置/重启。
#
# 背景（2026-11-14）：mcp-lite 的 token 曾指向「用户本人」账号，导致爸爸的
# 健康管家读到本人的 Garmin 数据。修复方式是服务器用爸爸账号独立登录一次，
# 生成独立 refresh 链；本脚本负责守住这个状态不再悄悄漂移。
#
# 检查两项（全部只读，绝不调用 garmin_* 工具 / 不做 login，避免推进 refresh 链）：
#   1. guid 是否仍是爸爸（8f5945a3f896），且不是本人（1347decc8a4e）
#   2. 近 30 分钟 SugarBee / Octop 日志是否有 Garmin 认证错误 ← 唯一可靠的故障信号
#
# 剩余有效期（LEFT）只写进日志供参考，**不作为告警依据**。理由见下方 LEFT 处注释：
# access token 只在有工具调用时才顺延，没人用就一定过期，那是常态。
#   历史教训：2026-11-14 曾按「exp<0 就告警」，2026-11-15 因爸爸一天没用
#   Garmin，半天内推了十几条「token 已过期」。refresh 链其实完全正常。
#
# 告警走 Bark，group=garmin，30 分钟限流；**只告警不重启、不改任何 token**。
# 部署：scripts/deploy_server.sh 自动同步到独立目录 /opt/garmin_ops/ 并幂等加 cron。
#       不能放 /opt/garmin_mcp_lite/ —— 那个目录在重建 venv 时会被整个删掉。
# 定时：*/10 * * * * /opt/garmin_ops/check_dad_token.sh >/dev/null 2>&1
set -u

TOKEN=${TOKEN:-/root/.garmin-mcp-lite/garmin_tokens.json}
BARK_KEY_FILE=${BARK_KEY_FILE:-/opt/sugar_bee/.bark_key}
STATE=/tmp/garmin_dad_guard.last
LOCK_MIN=30

DAD_GUID=8f5945a3f896
SELF_GUID=1347decc8a4e

log() { echo "[$(date '+%F %T %Z')] $*"; }

notify() {
  local title="$1" body="$2"
  [ -s "$BARK_KEY_FILE" ] || { log "WARN 无 Bark key，跳过推送: $title"; return 0; }
  # 30 分钟限流，避免把真故障刷成告警风暴
  if [ -f "$STATE" ]; then
    last=$(cat "$STATE" 2>/dev/null || echo 0)
    [ $(( $(date +%s) - last )) -lt $((LOCK_MIN * 60)) ] && return 0
  fi
  python3 - "$BARK_KEY_FILE" "$title" "$body" <<'PY' 2>/dev/null || true
import json, sys, urllib.request
key, title, body = sys.argv[1:4]
key = open(key).read().strip()
payload = json.dumps({"title": title, "body": body[:400], "level": "critical",
                      "group": "garmin"}).encode()
req = urllib.request.Request("https://api.day.app/" + key, data=payload,
                             headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=10)
PY
  date +%s > "$STATE"
  log "已推送告警: $title"
}

if [ ! -s "$TOKEN" ]; then
  notify "老愚 Garmin token 丢失" "$TOKEN 不存在或为空，健康管家无法查 Garmin 数据。需在服务器用爸爸账号重跑 garmin-mcp-lite-login。"
  exit 1
fi

# 只读解析 JWT；不 login、不调用任何 garmin 工具
INFO=$(python3 - "$TOKEN" <<'PY'
import json, base64, hashlib, sys, time
try:
    d = json.load(open(sys.argv[1])); t = d['di_token']
    p = t.split('.')[1]; p += '=' * (-len(p) % 4)
    o = json.loads(base64.urlsafe_b64decode(p))
    f = lambda s: hashlib.sha256(str(s).encode()).hexdigest()[:12]
    print(f(o.get('garmin_guid', '')), int(o.get('exp', 0)), int(time.time()))
except Exception as e:
    print('PARSE_FAIL', type(e).__name__, 0)
PY
)
GUID=$(printf '%s' "$INFO" | awk '{print $1}')
EXP=$(printf '%s' "$INFO" | awk '{print $2}')
NOW=$(printf '%s' "$INFO" | awk '{print $3}')

if [ "$GUID" = "PARSE_FAIL" ]; then
  notify "老愚 Garmin token 无法解析" "token 文件损坏或格式变化，需人工检查 $TOKEN"
  exit 1
fi
if [ "$GUID" != "$DAD_GUID" ]; then
  notify "老愚 Garmin 账号串号" "guid=$GUID（期望 $DAD_GUID 爸爸；$SELF_GUID 是本人）。健康管家可能读到他人数据，请立即检查 token 来源。"
  exit 1
fi

LEFT=$(( (EXP - NOW) / 3600 ))
# 2026-11-15 修正：**exp 过期 ≠ 需要重登**，不要再按它告警。
#   · di_token（access）只有约 24h 寿命，而且只在**真的发生工具调用**时才被
#     顺延。爸爸两天不查 Garmin，它必然过期——这是常态，不是故障。
#   · di_refresh_token 是长期凭据（base64 编码的 JSON，只有 refreshTokenValue
#     和 garminGuid，**没有 exp**），garminconnect 在首次调用时拿它换新 access。
#   · 实测（2026-11-15 23:02）：token 已过期 6.8h，执行一次 garmin_activities
#     即自动续期到 +25.7h，refreshTokenValue 也正常轮换，全程无需人工。
# 之前按 exp<0 告警的后果：仅仅因为"没人用"，就每 30 分钟推一条 Bark，
# 两天堆了十几条，把真故障的信噪比也拉低了。
# 真正的故障信号只有一个——refresh 链真断了，也就是调用报认证错误，见下方日志检查。

# 认证错误检测（只读日志，不触发任何 Garmin 调用）
# grep -c 无匹配时返回 1，用 `|| true` 保留其输出的 0，不要再用 `|| echo 0`（会变成 "0\n0"）
ERRS=$(docker logs --since 30m sugar-bee 2>&1 | grep -ciE 'GarminConnectAuthenticationError|401 Unauthorized' || true)
ERRS=$(printf '%s' "${ERRS:-0}" | head -1 | tr -cd '0-9'); ERRS=${ERRS:-0}
# Octop 日志不轮转，历史里本来就有切换前的 garmin 报错；必须按时间窗过滤，
# 否则每次巡检都会把旧故障重新告警一遍。
# 模式要覆盖 mcp-lite 自己的措辞（client.py:37 抛的是
# "Garmin token expired or authentication failed"），否则真断了也抓不到。
CUTOFF=$(date -d '30 minutes ago' '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')
OCTO=$(awk -v c="$CUTOFF" 'substr($0,1,19) >= c && /Garmin token expired|authentication failed|GarminConnectAuthenticationError|mcp load failed: garmin/ {n++} END {print n+0}' \
       /root/.octop/logs/octop.log 2>/dev/null || true)
OCTO=$(printf '%s' "${OCTO:-0}" | head -1 | tr -cd '0-9'); OCTO=${OCTO:-0}
if [ "$ERRS" -gt 0 ] || [ "$OCTO" -gt 0 ]; then
  notify "老愚 Garmin 认证异常" "近 30m SugarBee 错误=$ERRS，Octop 累计=$OCTO。这才是 refresh 链真断了的信号。只告警不重启；两条链分别处理，绝不互相复制 token。"
fi

log "OK guid=$GUID 剩余=${LEFT}h（无动作）"
exit 0
