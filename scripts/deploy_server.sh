#!/usr/bin/env bash
# 把 garmin-mcp-lite 部署到 Octop 服务器，供愚群的「老愚 · 健康管家」(JMG40) 使用。
#
# 背景（2026-11-13 故障）：Octop connector 里 `garmin` 指向
#   /opt/garmin_mcp_lite/bin/garmin-mcp-lite
# 但这个目录曾被清空，导致每次对话报
#   prepare_chat_mcp ... missing=['garmin'] / mcp load failed: garmin
# 且整轮 MCP 工具被跳过。当时没有任何部署脚本，文件消失后无人察觉。
#
# 为什么用这个路径：connector 已固定指向它，**只要恢复文件即可**，
# 不需要改 connector（put_custom_servers 会整份覆盖，容易误删 sbhealth/sugarwrite），
# 也不需要重启 Octop（stdio 子进程按会话拉起，重启会打断家人使用）。
#
# 服务器缺 python3-venv/ensurepip，不能 `python3 -m venv` 直接建带 pip 的环境：
# 用 `--without-pip` 建壳，再借 Octop venv 的 pip 26 `--python` 把包装进去。
# 好处：不动 apt、不污染系统 Python、与 Octop 依赖完全隔离。
#
# 用法：
#   ./scripts/deploy_server.sh                 部署/校验（已装且版本一致则跳过安装）
#   ./scripts/deploy_server.sh --with-token   额外同步本机 Garmin token
#   ./scripts/deploy_server.sh --dry-run       只打印将做什么
#   HOST=1.2.3.4 KEY=~/.ssh/xxx ./scripts/deploy_server.sh
#
# 前置：本机先 `uv build`（生成 dist/garmin_mcp_lite-*.whl）。
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HOST="${HOST:-$(cat "$HOME/.sugar_bee_host" 2>/dev/null || true)}"
KEY="${KEY:-$HOME/.ssh/sugar_bee_new_agent}"
REMOTE_USER="${REMOTE_USER:-root}"
VENV=/opt/garmin_mcp_lite
TOKEN_DIR=/root/.garmin-mcp-lite
PYPI="${PYPI:-https://pypi.tuna.tsinghua.edu.cn/simple}"

DRY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --with-token)
      echo "ERROR: --with-token 已永久禁用。" >&2
      echo "原因：本机 ~/.garmin-mcp-lite/ 存的是「用户本人」的 Garmin 会话，" >&2
      echo "同步它会让老愚(爸爸的)健康管家读到本人数据 —— 2026-11-14 的实际事故。" >&2
      echo "token 只能由服务器用爸爸账号独立登录产生：" >&2
      echo "  ssh -t <server> 'GARMIN_EMAIL=<dad> GARMIN_PASSWORD=<pw> \\" >&2
      echo "    GARMIN_IS_CN=0 GARMIN_TOKEN_DIR=/root/.garmin-mcp-lite \\" >&2
      echo "    /opt/garmin_mcp_lite/bin/garmin-mcp-lite-login'" >&2
      echo "绝不从 SugarBee 的 .garmin_tokens/ 复制文件（同一 refresh 链会互踢）。" >&2
      exit 2 ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "未知参数: $a" >&2; exit 2 ;;
  esac
done

[ -n "$HOST" ] || { echo "ERROR: 未设置 HOST，且 ~/.sugar_bee_host 为空" >&2; exit 1; }
WHEEL=$(ls -1t "$HERE"/dist/garmin_mcp_lite-*.whl 2>/dev/null | head -1)
[ -n "$WHEEL" ] || { echo "ERROR: 找不到 wheel，先跑 uv build" >&2; exit 1; }
VERSION=$(basename "$WHEEL" | sed -E 's/garmin_mcp_lite-([0-9.]+)-.*/\1/')
SSH_OPTS=(-o IdentitiesOnly=yes -o ConnectTimeout=10 -o BatchMode=yes)
[ -f "$KEY" ] && SSH_OPTS+=(-i "$KEY")
SSH_TARGET="${REMOTE_USER}@${HOST}"

echo "目标: $SSH_TARGET"
echo "版本: $VERSION  wheel: $(basename "$WHEEL")"
echo "远端 venv: $VENV"
echo "token: 脚本永不同步（只能由服务器用爸爸账号独立登录产生）"
if [ "$DRY" = 1 ]; then
  echo "[dry-run] 将：检查远端版本 → 必要时重建 venv 并装 wheel → 用 Octop 加载路径验证"
  echo "[dry-run] 不会改 connector、不会重启 Octop、不会发任何消息、不会动 token"
  exit 0
fi

# ---- 1. 远端当前版本（一致且可执行文件在，就跳过安装，零中断）----
CURRENT=$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
  "$VENV/bin/python -c 'import importlib.metadata as m; print(m.version(\"garmin-mcp-lite\"))' 2>/dev/null" || true)
READY=0
if [ "$CURRENT" = "$VERSION" ] && ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
     "[ -x $VENV/bin/garmin-mcp-lite ]" 2>/dev/null; then
  echo "远端已是 $VERSION 且可执行文件在，跳过安装"
  READY=1
fi

if [ "$READY" = 0 ]; then
  echo "安装 $VERSION ..."
  scp -q "${SSH_OPTS[@]}" "$WHEEL" "$SSH_TARGET:/tmp/$(basename "$WHEEL")"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'bash -s' <<REMOTE
set -e
rm -rf $VENV
python3 -m venv --without-pip $VENV
# pip 26 的 --python 必须放在子命令 install 之前
/root/.octop/venv/bin/python -m pip --python $VENV/bin/python \
  install --quiet --disable-pip-version-check -i "$PYPI" /tmp/$(basename "$WHEEL")
rm -f /tmp/$(basename "$WHEEL")
[ -x $VENV/bin/garmin-mcp-lite ] || { echo "!! 可执行文件未生成" >&2; exit 1; }
echo "  已安装: \$($VENV/bin/python -c 'import importlib.metadata as m; print(m.version("garmin-mcp-lite"))')"
REMOTE
fi

# ---- 2. token 闸门：绝不从本机同步（见 --with-token 的错误说明）----
# 账号归属必须在每次 deploy 后复查：本机 ~/.garmin-mcp-lite/ 是本人账号，
# 服务器 /root/.garmin-mcp-lite/ 必须是爸爸账号 guid 8f5945a3f896。
echo "校验远端 token 账号归属（只读，不调用任何 garmin 工具）..."
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'bash -s' <<'REMOTE'
D=/tmp/garmin_deploy_probe
install -d -m 700 "$D"
cp -a /root/.garmin-mcp-lite/garmin_tokens.json "$D/probe.json"
python3 - "$D/probe.json" <<'PY'
import json,base64,hashlib,sys
f=lambda s:hashlib.sha256(str(s).encode()).hexdigest()[:12]
d=json.load(open(sys.argv[1])); t=d['di_token']
p=t.split('.')[1]; p+='='*(-len(p)%4)
g=f(json.loads(base64.urlsafe_b64decode(p)).get('garmin_guid',''))
print('  garmin_guid =',g)
if g != '8f5945a3f896':
    print('  !! 账号不是爸爸（可能是本人或旧会话），禁止继续部署', file=sys.stderr)
    sys.exit(1)
print('  OK: 爸爸账号')
PY
rm -rf "$D"
REMOTE

# ---- 3. 走 Octop 真实加载路径验证（不发消息、不改数据、不重启）----
echo "用 Octop 的 custom_harness_configs → aload_mcp_tools 验证 ..."
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'bash -s' <<'REMOTE'
HOME=/root /root/.octop/venv/bin/python - <<'PY'
import asyncio, sys
sys.path.insert(0, '/root/.octop/venv/lib/python3.12/site-packages')
from pathlib import Path
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.connectors.service import ConnectorService
from octop_harness.mcp import aload_mcp_tools

USER_ID = 3  # 愚群 yzq0535，JMG40 健康管家
db = SqlitePool(Path('/root/.octop/octop.db'))
svc = ConnectorService(repo=ConnectorRepo(db), secret_repo=SecretRepo(db),
                       settings_repo=SettingsRepo(db), config=None)
configs = svc.custom_harness_configs(USER_ID)
assert 'garmin' in configs, 'connector 里没有 garmin'
assert 'sbhealth' in configs and 'sugarwrite' in configs, '另外两个 MCP 被误删！'

async def main():
    tools = await aload_mcp_tools({'garmin': configs['garmin']})
    names = [getattr(t, 'name', '') for t in tools]
    assert len(names) >= 20, f'工具数异常: {len(names)}'
    assert any('garmin_garmin_health' in n for n in names), '缺 garmin_health'
    assert any('garmin_garmin_status' in n for n in names), '缺 garmin_status'
    print(f'  OK: {len(names)} 个工具注册成功，含 garmin_status / garmin_health')
asyncio.run(main())
PY
REMOTE

echo
echo "完成。未改 connector、未重启 Octop、未发送任何消息。"
echo "下一次对话会自动重新加载（aload_mcp_tools 失败时不写缓存）。"
echo "观察日志确认无新报错: grep 'missing=.*garmin' /root/.octop/logs/octop.log | tail -3"
