"""Tests for the Garmin client factory.

These are deliberately reload-free: the previous version of this file called
`importlib.reload()` on the client module, which left every tool module holding
a reference to the *old* `get_client` and made the suite order-dependent. That
is why CI had to filter these out with `-k 'not test_get_client'`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garmin_mcp_lite import client as client_mod

TOKEN_PATH = "/fake/garmin-mcp-lite/garmin_tokens.json"
TOKEN_DIR = "/fake/garmin-mcp-lite"


class _FakeTokenFile:
    """Stands in for the token Path; only `.exists()` and `str()` are used."""

    def __init__(self, exists: bool = True, path: str = TOKEN_PATH) -> None:
        self._exists = exists
        self._path = path

    def exists(self) -> bool:
        return self._exists

    def __str__(self) -> str:
        return self._path


@pytest.fixture()
def garmin_cls(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch the Garmin constructor and point the token file at a present file."""
    fake_instance = MagicMock()
    fake_cls = MagicMock(return_value=fake_instance)
    fake_cls.instance = fake_instance  # type: ignore[attr-defined]

    monkeypatch.setattr(client_mod, "Garmin", fake_cls)
    monkeypatch.setattr(client_mod, "TOKEN_DIR", TOKEN_DIR)
    monkeypatch.setattr(client_mod, "TOKEN_FILE", _FakeTokenFile())
    monkeypatch.setattr(client_mod, "_client", None)
    return fake_cls


class TestClientFactory:
    def test_returns_garmin_instance(self, garmin_cls: MagicMock) -> None:
        assert client_mod.get_client() is garmin_cls.instance  # type: ignore[attr-defined]

    def test_is_a_singleton(self, garmin_cls: MagicMock) -> None:
        first = client_mod.get_client()
        second = client_mod.get_client()
        assert first is second
        garmin_cls.assert_called_once()

    def test_logs_in_with_the_token_dir(self, garmin_cls: MagicMock) -> None:
        client_mod.get_client()
        garmin_cls.instance.login.assert_called_once_with(TOKEN_DIR)  # type: ignore[attr-defined]


class TestTokenMissing:
    def test_raises_with_login_instructions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(client_mod, "TOKEN_FILE", _FakeTokenFile(exists=False))
        monkeypatch.setattr(client_mod, "Garmin", MagicMock())
        monkeypatch.setattr(client_mod, "_client", None)

        with pytest.raises(RuntimeError) as excinfo:
            client_mod.get_client()

        message = str(excinfo.value)
        assert "token not found" in message
        # This message is the only onboarding hint a new user gets, so it has to
        # name the file it looked for and the command that creates it.
        assert TOKEN_PATH in message
        assert "garmin_mcp_lite.login" in message


class TestLoginFailures:
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (GarminConnectAuthenticationError("bad creds"), "token expired"),
            (GarminConnectTooManyRequestsError("429"), "Too many requests"),
            (GarminConnectConnectionError("offline"), "Garmin connection error"),
        ],
    )
    def test_wraps_into_runtime_error(
        self, garmin_cls: MagicMock, error: Exception, expected: str
    ) -> None:
        garmin_cls.instance.login.side_effect = error  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError) as excinfo:
            client_mod.get_client()

        assert expected in str(excinfo.value)
        assert excinfo.value.__cause__ is error

    def test_failed_login_does_not_cache_the_client(self, garmin_cls: MagicMock) -> None:
        garmin_cls.instance.login.side_effect = GarminConnectConnectionError("offline")  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError):
            client_mod.get_client()

        assert client_mod._client is None


class TestChinaRegionFlag:
    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes"])
    def test_truthy_values_enable_cn(
        self, garmin_cls: MagicMock, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("GARMIN_IS_CN", value)
        client_mod.get_client()
        assert garmin_cls.call_args.kwargs["is_cn"] is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "random"])
    def test_other_values_leave_cn_off(
        self, garmin_cls: MagicMock, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("GARMIN_IS_CN", value)
        client_mod.get_client()
        assert garmin_cls.call_args.kwargs["is_cn"] is False

    def test_unset_means_international(
        self, garmin_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GARMIN_IS_CN", raising=False)
        client_mod.get_client()
        assert garmin_cls.call_args.kwargs["is_cn"] is False
