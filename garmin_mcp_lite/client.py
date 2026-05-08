import os
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# Token directory: read from environment variable, or default to ~/.garmin-mcp-lite
TOKEN_DIR = Path(os.environ.get("GARMIN_TOKEN_DIR", Path.home() / ".garmin-mcp-lite"))
TOKEN_FILE = TOKEN_DIR / "garmin_tokens.json"

_client: Garmin | None = None


def get_client() -> Garmin:
    """Return a logged-in Garmin client (singleton, reuses cached token)."""
    global _client
    if _client is not None:
        return _client

    if not TOKEN_FILE.exists():
        raise RuntimeError(
            f"Garmin token not found ({TOKEN_FILE}). Please run the login script first:\n"
            f"  GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=xxx python -m garmin_mcp_lite.login"
        )

    is_cn = os.environ.get("GARMIN_IS_CN", "").lower() in ("1", "true", "yes")
    client = Garmin(is_cn=is_cn)

    try:
        client.login(str(TOKEN_DIR))
    except GarminConnectAuthenticationError as e:
        raise RuntimeError(
            f"Garmin token expired or authentication failed ({e}). Please re-run the login script:\n"
            f"  GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=xxx python -m garmin_mcp_lite.login"
        ) from e
    except GarminConnectTooManyRequestsError as e:
        raise RuntimeError("Too many requests to Garmin. Please try again later.") from e
    except GarminConnectConnectionError as e:
        raise RuntimeError(f"Garmin connection error: {e}") from e

    _client = client
    return client
