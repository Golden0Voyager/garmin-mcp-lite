from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def patched_client() -> MagicMock:
    """Fully mock garminconnect and token path so client.get_client() is runnable."""
    fake_garmin = MagicMock()
    fake_garmin.login.return_value = None

    with (
        patch("garmin_mcp_lite.client.Garmin", return_value=fake_garmin) as mock_garmin_cls,
        patch("garmin_mcp_lite.client.TOKEN_FILE", Path("/tmp/test_token.json")),
        patch("pathlib.Path.exists", return_value=True),
    ):
        import garmin_mcp_lite.client as client_mod

        importlib.reload(client_mod)

        # Reset singleton so get_client() runs fresh
        client_mod._client = None

        yield mock_garmin_cls


class TestClient:
    def test_get_client_returns_garmin_instance(self, patched_client: MagicMock) -> None:
        from garmin_mcp_lite.client import get_client

        client = get_client()
        assert client is not None

    def test_get_client_singleton(self, patched_client: MagicMock) -> None:
        from garmin_mcp_lite.client import get_client

        c1 = get_client()
        c2 = get_client()
        assert c1 is c2

    def test_get_client_caches_token(self, patched_client: MagicMock) -> None:
        from garmin_mcp_lite.client import get_client

        c1 = get_client()
        c2 = get_client()
        assert c1 is c2
