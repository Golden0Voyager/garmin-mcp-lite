import os
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_DIR = Path.home() / ".garmin-mcp-lite"
TOKEN_FILE = TOKEN_DIR / "garmin_tokens.json"

_client: Garmin | None = None


def get_client() -> Garmin:
    """获取已登录的 Garmin 客户端（单例，token 缓存复用）。

    首次使用请先运行登录脚本生成 token：
        GARMIN_EMAIL=xxx GARMIN_PASSWORD=yyy python -m garmin_mcp_lite.login
    """
    global _client
    if _client is not None:
        return _client

    if not TOKEN_FILE.exists():
        raise RuntimeError(
            f"未找到 Garmin token ({TOKEN_FILE})。请先执行登录：\n"
            f"  GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=xxx python -m garmin_mcp_lite.login"
        )

    is_cn = os.environ.get("GARMIN_IS_CN", "").lower() in ("1", "true", "yes")
    client = Garmin(is_cn=is_cn)

    try:
        client.login(str(TOKEN_DIR))
    except GarminConnectAuthenticationError as e:
        raise RuntimeError(
            f"Garmin token 失效或认证失败（{e}）。请重新登录：\n"
            f"  GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=xxx python -m garmin_mcp_lite.login"
        ) from e
    except GarminConnectTooManyRequestsError as e:
        raise RuntimeError("Garmin 请求过于频繁，稍后再试") from e
    except GarminConnectConnectionError as e:
        raise RuntimeError(f"Garmin 连接错误：{e}") from e

    _client = client
    return client
