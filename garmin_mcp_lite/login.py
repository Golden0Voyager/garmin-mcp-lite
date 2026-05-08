"""
Garmin interactive login script (run once to cache a session token).

Usage:
    GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=xxx python -m garmin_mcp_lite.login

Steps:
1. Reads GARMIN_EMAIL / GARMIN_PASSWORD / GARMIN_IS_CN from environment variables.
2. Attempts login; prompts interactively for an MFA code if Garmin requires it.
3. Saves the session token to ~/.garmin-mcp-lite/garmin_tokens.json on success.

After a successful first login you don't need to run this again (token is valid ~1 year).
"""
import os
import sys

from garminconnect import Garmin, GarminConnectAuthenticationError

TOKEN_DIR = os.environ.get("GARMIN_TOKEN_DIR", os.path.expanduser("~/.garmin-mcp-lite"))


def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("❌ Please set the GARMIN_EMAIL and GARMIN_PASSWORD environment variables.")
        sys.exit(1)

    is_cn = os.environ.get("GARMIN_IS_CN", "").lower() in ("1", "true", "yes")
    domain_hint = "garmin.cn" if is_cn else "garmin.com"
    print(f"🔐 Logging in to Garmin ({domain_hint}): {email}")

    os.makedirs(TOKEN_DIR, exist_ok=True)
    client = Garmin(email=email, password=password, is_cn=is_cn)

    try:
        client.login(TOKEN_DIR)
    except GarminConnectAuthenticationError as e:
        print(f"❌ Authentication failed: {e}")
        print("Possible causes: wrong credentials / account temporarily locked / try logging in via browser first to clear CAPTCHA.")
        sys.exit(1)
    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate" in msg.lower():
            print(f"❌ IP rate-limited by Garmin: {e}")
            print("Suggestions:")
            print("  1. Install curl_cffi for better login strategies: uv pip install curl-cffi")
            print("  2. Switch to a mobile hotspot or wait 6-12 hours.")
            print("  3. Log in via browser first: https://connect.garmin.com or https://connect.garmin.cn")
            print("  4. If you have a China account, prefix the command with GARMIN_IS_CN=true")
        else:
            print(f"❌ Login error: {e}")
        sys.exit(1)

    try:
        full_name = client.get_full_name()
        print(f"✅ Login successful: {full_name}")
    except Exception:
        print("✅ Login successful")
    print(f"📁 Token saved to {TOKEN_DIR}/garmin_tokens.json")
    print("\nThe MCP server will use this token automatically. No need to log in again.")


if __name__ == "__main__":
    main()
