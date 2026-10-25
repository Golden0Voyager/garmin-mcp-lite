"""Tests for the garmin-mcp-lite-setup walkthrough.

Everything with a side effect (probes, Garmin login, the Xiaomi flow, stdin)
is patched, so these run without network, credentials or a terminal.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp_lite import setup
from garmin_mcp_lite.login import LoginError

_GARMIN_OK: dict[str, Any] = {"ok": True, "token_file": "/fake/g", "next": None, "account": "Test User", "detail": "token valid"}
_GARMIN_MISSING: dict[str, Any] = {"ok": False, "token_file": "/fake/g", "next": "garmin-mcp-lite-login", "detail": "No Garmin token"}
_XIAOMI_OK: dict[str, Any] = {"ok": True, "optional": True, "needed_for": "garmin_sync_weight", "token_file": "/fake/x", "next": None, "detail": "token valid"}
_XIAOMI_MISSING: dict[str, Any] = {"ok": False, "optional": True, "needed_for": "garmin_sync_weight", "token_file": "/fake/x", "next": "garmin-mcp-lite-xiaomi-login", "detail": "No Mi Fitness token"}


@pytest.fixture()
def no_env_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)


class TestGarminStep:
    def test_valid_token_never_prompts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_OK))
        monkeypatch.setattr(setup, "probe_xiaomi", lambda: dict(_XIAOMI_OK))
        asked = MagicMock()
        monkeypatch.setattr("builtins.input", asked)
        login = MagicMock()
        monkeypatch.setattr(setup, "run_login", login)
        assert setup.main() == 0
        asked.assert_not_called()
        login.assert_not_called()

    def test_credentials_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_MISSING))
        monkeypatch.setattr(setup, "probe_xiaomi", lambda: dict(_XIAOMI_OK))
        monkeypatch.setenv("GARMIN_EMAIL", "you@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "hunter2")
        login = MagicMock()
        monkeypatch.setattr(setup, "run_login", login)
        assert setup.main() == 0
        login.assert_called_once_with("you@example.com", "hunter2")

    def test_credentials_typed_interactively(
        self, monkeypatch: pytest.MonkeyPatch, no_env_credentials: None
    ) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_MISSING))
        monkeypatch.setattr(setup, "probe_xiaomi", lambda: dict(_XIAOMI_OK))
        monkeypatch.setattr("builtins.input", lambda prompt="": "you@example.com")
        monkeypatch.setattr("getpass.getpass", lambda *args, **kwargs: "hunter2")
        login = MagicMock()
        monkeypatch.setattr(setup, "run_login", login)
        assert setup.main() == 0
        login.assert_called_once_with("you@example.com", "hunter2")

    def test_login_failure_exits_nonzero_with_the_hint(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_MISSING))
        monkeypatch.setenv("GARMIN_EMAIL", "you@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "hunter2")
        monkeypatch.setattr(
            setup, "run_login", MagicMock(side_effect=LoginError("Authentication failed: bad creds", hint="clear the CAPTCHA first"))
        )
        assert setup.main() == 1
        output = capsys.readouterr().out
        assert "Authentication failed" in output
        assert "clear the CAPTCHA first" in output

    def test_ctrl_c_at_credentials_prompt_cancels(
        self, monkeypatch: pytest.MonkeyPatch, no_env_credentials: None
    ) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_MISSING))

        def interrupted(prompt: str = "") -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", interrupted)
        assert setup.main() == 1


class TestXiaomiStep:
    def test_declining_is_not_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_OK))
        monkeypatch.setattr(setup, "probe_xiaomi", lambda: dict(_XIAOMI_MISSING))
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        with patch.object(setup.xiaomi_login, "run") as xiaomi_run:
            assert setup.main() == 0
        xiaomi_run.assert_not_called()

    def test_accepting_runs_the_interactive_login(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_OK))
        monkeypatch.setattr(setup, "probe_xiaomi", lambda: dict(_XIAOMI_MISSING))
        monkeypatch.setattr("builtins.input", lambda prompt="": "y")
        with patch.object(setup.xiaomi_login, "run", return_value=0) as xiaomi_run:
            assert setup.main() == 0
        xiaomi_run.assert_called_once_with()

    def test_xiaomi_login_failure_exits_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_OK))
        monkeypatch.setattr(setup, "probe_xiaomi", lambda: dict(_XIAOMI_MISSING))
        monkeypatch.setattr("builtins.input", lambda prompt="": "y")
        with patch.object(setup.xiaomi_login, "run", return_value=1):
            assert setup.main() == 1

    def test_ctrl_c_at_the_xiaomi_prompt_cancels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup, "probe_garmin", lambda: dict(_GARMIN_OK))
        monkeypatch.setattr(setup, "probe_xiaomi", lambda: dict(_XIAOMI_MISSING))

        def interrupted(prompt: str = "") -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", interrupted)
        assert setup.main() == 1
