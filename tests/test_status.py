"""Tests for the login probes behind garmin_status and garmin-mcp-lite-setup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp_lite import onboarding
from garmin_mcp_lite.onboarding import probe_garmin, probe_xiaomi
from garmin_mcp_lite.tools.status import get_status
from garmin_mcp_lite.xiaomi import XiaomiError

_TOKEN = {"userId": "42", "passToken": "pt", "ssecurity": "ss"}


class _FakeTokenFile:
    """Stands in for the token Path; only `.exists()` and `str()` are used."""

    def __init__(self, path: str, exists: bool) -> None:
        self._path = path
        self._exists = exists

    def exists(self) -> bool:
        return self._exists

    def __str__(self) -> str:
        return self._path


@pytest.fixture()
def garmin_token_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # The probes must never consult the developer's real token directory.
    monkeypatch.setattr(onboarding, "TOKEN_FILE", _FakeTokenFile("/fake/tokens/garmin_tokens.json", exists=True))


class TestProbeGarmin:
    def test_missing_token_names_the_file_and_the_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(onboarding, "TOKEN_FILE", _FakeTokenFile("/fake/tokens/garmin_tokens.json", exists=False))
        result = probe_garmin()
        assert result["ok"] is False
        assert result["next"] == onboarding.GARMIN_LOGIN_CMD
        assert "/fake/tokens/garmin_tokens.json" in result["detail"]

    def test_expired_token_passes_the_get_client_message_through(self, garmin_token_present: None) -> None:
        with patch(
            "garmin_mcp_lite.onboarding.get_client",
            side_effect=RuntimeError("Garmin token expired or authentication failed. re-run the login script"),
        ):
            result = probe_garmin()
        assert result["ok"] is False
        assert "re-run the login script" in result["detail"]
        assert result["next"] == onboarding.GARMIN_LOGIN_CMD

    def test_valid_token_reports_the_account(self, garmin_token_present: None, mock_get_client: MagicMock) -> None:
        mock_get_client.get_full_name.return_value = "Test User"
        assert probe_garmin() == {
            "ok": True,
            "token_file": "/fake/tokens/garmin_tokens.json",
            "next": None,
            "account": "Test User",
            "detail": "token valid",
        }


class TestProbeXiaomi:
    @pytest.fixture()
    def token_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(onboarding, "TOKEN_PATH", _FakeTokenFile("/fake/tokens/xiaomi.json", exists=True))
        monkeypatch.setattr(onboarding, "load_token", lambda: dict(_TOKEN))
        monkeypatch.setattr(onboarding, "save_token", MagicMock())

    def test_missing_token_is_optional_and_names_the_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(onboarding, "TOKEN_PATH", _FakeTokenFile("/fake/tokens/xiaomi.json", exists=False))
        monkeypatch.setattr(onboarding, "load_token", lambda: None)
        result = probe_xiaomi()
        assert result["ok"] is False
        assert result["optional"] is True
        assert result["needed_for"] == "garmin_sync_weight"
        assert result["next"] == onboarding.XIAOMI_LOGIN_CMD
        assert "/fake/tokens/xiaomi.json" in result["detail"]

    def test_expired_token_carries_the_relogin_hint(self, token_present: None, monkeypatch: pytest.MonkeyPatch) -> None:
        cloud = MagicMock()
        cloud.refresh.side_effect = XiaomiError(
            "Mi Fitness token is no longer valid. Run `garmin-mcp-lite-xiaomi-login` again."
        )
        monkeypatch.setattr(onboarding, "MiCloud", MagicMock(return_value=cloud))
        result = probe_xiaomi()
        assert result["ok"] is False
        assert "xiaomi-login" in result["detail"]

    def test_network_trouble_is_reported_not_raised(self, token_present: None, monkeypatch: pytest.MonkeyPatch) -> None:
        cloud = MagicMock()
        cloud.refresh.side_effect = OSError("dns gone")
        monkeypatch.setattr(onboarding, "MiCloud", MagicMock(return_value=cloud))
        result = probe_xiaomi()
        assert result["ok"] is False
        assert "Could not reach Mi Fitness" in result["detail"]

    def test_valid_token_rotates_and_saves(self, token_present: None, monkeypatch: pytest.MonkeyPatch) -> None:
        rotated = {**_TOKEN, "passToken": "new"}
        cloud = MagicMock()
        cloud.refresh.return_value = rotated
        monkeypatch.setattr(onboarding, "MiCloud", MagicMock(return_value=cloud))
        saved: list[dict] = []
        monkeypatch.setattr(onboarding, "save_token", saved.append)
        result = probe_xiaomi()
        assert result["ok"] is True
        assert result["next"] is None
        assert saved == [rotated]


class TestGetStatus:
    def test_ready_reflects_garmin_only(self) -> None:
        # A user with no Xiaomi scale must not be told setup is incomplete.
        with (
            patch("garmin_mcp_lite.tools.status.probe_garmin", return_value={"ok": True}),
            patch("garmin_mcp_lite.tools.status.probe_xiaomi", return_value={"ok": False, "optional": True}),
        ):
            result = get_status()
        assert result["ready"] is True
        assert result["garmin"]["ok"] is True
        assert result["xiaomi"]["optional"] is True

    def test_missing_garmin_token_is_not_ready(self) -> None:
        with (
            patch("garmin_mcp_lite.tools.status.probe_garmin", return_value={"ok": False, "detail": "no token"}),
            patch("garmin_mcp_lite.tools.status.probe_xiaomi", return_value={"ok": True}),
        ):
            result = get_status()
        assert result["ready"] is False
