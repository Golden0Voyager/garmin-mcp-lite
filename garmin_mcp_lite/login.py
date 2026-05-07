"""
Garmin 交互式登录脚本（一次性跑）

用法：
    GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=xxx python -m garmin_mcp_lite.login

流程：
1. 从环境变量读 GARMIN_EMAIL / GARMIN_PASSWORD / GARMIN_IS_CN
2. 尝试登录；若 Garmin 要 MFA 则交互式提示输入验证码
3. 成功后把 token 存到 ~/.garmin-mcp-lite/garmin_tokens.json

首次成功后就不用再跑了（token 有效期约 1 年）。
"""
import os
import sys

from garminconnect import Garmin, GarminConnectAuthenticationError

TOKEN_DIR = os.path.expanduser("~/.garmin-mcp-lite")


def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("❌ 请提供环境变量 GARMIN_EMAIL / GARMIN_PASSWORD")
        sys.exit(1)

    is_cn = os.environ.get("GARMIN_IS_CN", "").lower() in ("1", "true", "yes")
    domain_hint = "garmin.cn" if is_cn else "garmin.com"
    print(f"🔐 尝试登录 Garmin ({domain_hint}): {email}")

    os.makedirs(TOKEN_DIR, exist_ok=True)
    client = Garmin(email=email, password=password, is_cn=is_cn)

    try:
        client.login(TOKEN_DIR)
    except GarminConnectAuthenticationError as e:
        print(f"❌ 认证失败：{e}")
        print("可能原因：账号密码错误 / 账号被临时锁定 / 浏览器登录一次清除人机验证")
        sys.exit(1)
    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate" in msg.lower():
            print(f"❌ IP 被 Garmin 限流：{e}")
            print("建议：")
            print("  1. 安装 curl_cffi 启用更多登录策略：uv pip install curl-cffi")
            print("  2. 换手机热点 / 等 6-12 小时")
            print("  3. 先浏览器登录 https://connect.garmin.com 或 https://connect.garmin.cn")
            print("  4. 如果账号是中国区，添加 GARMIN_IS_CN=true")
        else:
            print(f"❌ 登录异常：{e}")
        sys.exit(1)

    try:
        full_name = client.get_full_name()
        print(f"✅ 登录成功：{full_name}")
    except Exception:
        print("✅ 登录成功")
    print(f"📁 Token 已保存到 {TOKEN_DIR}/garmin_tokens.json")
    print("\n后续 MCP 服务器会自动使用此 token，无需再次登录。")


if __name__ == "__main__":
    main()
