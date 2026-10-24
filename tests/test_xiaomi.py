"""Tests for the Mi Fitness client.

The signing path is tested by round-trip rather than by comparing against a
recorded signature: a fake session decrypts the request it receives using the
known ssecurity and the nonce carried in the request itself, then encrypts its
reply the same way. That proves the whole chain (nonce shape, RC4, both SHA1
bindings, response decoding) without freezing a timestamp-dependent fixture.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from requests.cookies import RequestsCookieJar

from garmin_mcp_lite import xiaomi


@pytest.fixture()
def tmp_dir():
    """A writable directory outside pytest's tmp_path.

    The sandbox denies the mkdir pytest performs under /private/var/folders, so
    tmp_path cannot be used here; /tmp is writable.
    """
    path = Path(tempfile.mkdtemp(dir="/tmp"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


SUSER_ID = "1234567890"
PASS_TOKEN = "pass-token-value"
SSECURITY = base64.b64encode(b"super-secret-ssecurity").decode()


def _token() -> dict[str, str]:
    return {"userId": SUSER_ID, "passToken": PASS_TOKEN, "ssecurity": SSECURITY}


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, headers: dict | None = None) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self.content = text.encode()
        self.cookies = _jar()
        self.history: list = []


def _jar(**cookies: str) -> RequestsCookieJar:
    """A real RequestsCookieJar, so duplicate-name behaviour matches production."""
    jar = RequestsCookieJar()
    for name, value in cookies.items():
        jar.set(name, value, domain=".xiaomi.com", path="/")
    return jar


class FakeSession:
    """Decrypts each request and encrypts each reply, like the real server."""

    def __init__(self, ssecurity: bytes, reply: dict) -> None:
        self.ssecurity = ssecurity
        self.reply = reply
        self.seen: list[dict] = []
        self.cookies = MagicMock()
        self.cookies.get_dict.return_value = {}

    def post(self, url, data=None, headers=None, timeout=None):
        nonce = base64.b64decode(data["_nonce"])
        signed = hashlib.sha256(self.ssecurity + nonce).digest()
        plaintext = xiaomi._rc4(signed, base64.b64decode(data["data"]))
        self.seen.append({"url": url, "payload": json.loads(plaintext), "form": data})
        cipher = base64.b64encode(xiaomi._rc4(signed, json.dumps(self.reply).encode())).decode()
        return FakeResponse(cipher)


class TestRc4:
    def test_roundtrip(self) -> None:
        key = hashlib.sha256(b"key").digest()
        payload = b'{"key":"weight"}'
        assert xiaomi._rc4(key, xiaomi._rc4(key, payload)) == payload

    def test_is_not_identity(self) -> None:
        key = hashlib.sha256(b"key").digest()
        assert xiaomi._rc4(key, b"plaintext") != b"plaintext"


class TestParseAuth:
    def test_strips_the_marker(self) -> None:
        assert xiaomi._parse_auth(b'&&&START&&&{"code":0}') == {"code": 0}

    def test_accepts_plain_json(self) -> None:
        assert xiaomi._parse_auth(b'{"code":0}') == {"code": 0}

    def test_rejects_garbage(self) -> None:
        with pytest.raises(xiaomi.XiaomiError):
            xiaomi._parse_auth(b"<html>nope</html>")


class TestTokenStorage:
    def test_load_returns_none_when_absent(self, tmp_dir, monkeypatch) -> None:
        monkeypatch.setattr(xiaomi, "TOKEN_PATH", tmp_dir / "missing.json")
        assert xiaomi.load_token() is None

    def test_load_returns_none_on_broken_json(self, tmp_dir, monkeypatch) -> None:
        path = tmp_dir / "xiaomi.json"
        path.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(xiaomi, "TOKEN_PATH", path)
        assert xiaomi.load_token() is None

    def test_load_returns_none_when_a_field_is_blank(self, tmp_dir, monkeypatch) -> None:
        # A half-written file must not look like a usable token, otherwise every
        # sync fails deep inside the signing code instead of at the login prompt.
        path = tmp_dir / "xiaomi.json"
        path.write_text(json.dumps({"userId": "1", "passToken": "", "ssecurity": "x"}), encoding="utf-8")
        monkeypatch.setattr(xiaomi, "TOKEN_PATH", path)
        assert xiaomi.load_token() is None

    def test_save_then_load(self, tmp_dir, monkeypatch) -> None:
        path = tmp_dir / "nested" / "xiaomi.json"
        monkeypatch.setattr(xiaomi, "TOKEN_PATH", path)
        assert xiaomi.save_token(_token()) == path
        assert xiaomi.load_token() == _token()

    def test_save_restricts_permissions(self, tmp_dir, monkeypatch) -> None:
        path = tmp_dir / "xiaomi.json"
        monkeypatch.setattr(xiaomi, "TOKEN_PATH", path)
        xiaomi.save_token(_token())
        assert oct(os.stat(path).st_mode)[-3:] == "600"


class TestRefresh:
    def _cloud(self) -> xiaomi.MiCloud:
        cloud = xiaomi.MiCloud(_token())
        cloud.session = MagicMock()
        return cloud

    def test_updates_the_token_and_clock_offset(self) -> None:
        cloud = self._cloud()
        rotated = base64.b64encode(b"rotated-ssecurity").decode()
        cloud.session.get.side_effect = [
            FakeResponse(
                '&&&START&&&'
                + json.dumps({"code": 0, "userId": 42, "passToken": "new", "ssecurity": rotated, "location": "https://x"})
            ),
            FakeResponse("ok", headers={"Date": "Sat, 24 Oct 2026 03:00:00 GMT"}),
        ]

        token = cloud.refresh()

        assert token["userId"] == "42"
        assert token["passToken"] == "new"
        assert base64.b64decode(token["ssecurity"]) == b"rotated-ssecurity"
        # The nonce embeds a minute-resolution clock, so a skewed host clock
        # breaks every later request. The offset must actually be computed.
        assert cloud.time_offset != 0.0

    def test_reports_an_expired_token(self) -> None:
        cloud = self._cloud()
        cloud.session.get.return_value = FakeResponse('&&&START&&&{"code":70016,"desc":"auth error"}')

        with pytest.raises(xiaomi.XiaomiError, match="no longer valid"):
            cloud.refresh()

    def test_keeps_the_token_when_the_reply_omits_fields(self) -> None:
        cloud = self._cloud()
        cloud.session.get.return_value = FakeResponse('&&&START&&&{"code":0}')

        token = cloud.refresh()

        assert token == _token()
        assert cloud.time_offset == 0.0


class TestSignedPost:
    def test_signs_and_decodes_the_round_trip(self) -> None:
        cloud = xiaomi.MiCloud(_token())
        fake = FakeSession(base64.b64decode(SSECURITY), {"code": 0, "result": {"ok": True}})
        cloud.session = fake

        assert cloud._post("/app/v1/data/get_fitness_data_by_time", {"key": "weight"}) == {
            "code": 0,
            "result": {"ok": True},
        }

        sent = fake.seen[0]
        assert sent["payload"] == {"key": "weight"}
        # All four fields the protocol requires must be present.
        assert set(sent["form"]) == {"data", "rc4_hash__", "signature", "_nonce"}
        assert len(base64.b64decode(sent["form"]["_nonce"])) == 12

    def test_falls_back_to_plain_json_on_error(self) -> None:
        cloud = xiaomi.MiCloud(_token())
        cloud.session = MagicMock()
        cloud.session.cookies.get_dict.return_value = {}
        cloud.session.post.return_value = FakeResponse('{"code":401}')

        assert cloud._post("/x", {}) == {"code": 401}

    def test_reports_http_failure(self) -> None:
        cloud = xiaomi.MiCloud(_token())
        cloud.session = MagicMock()
        cloud.session.post.return_value = FakeResponse("denied", status_code=403)

        with pytest.raises(xiaomi.XiaomiError, match="HTTP 403"):
            cloud._post("/x", {})

    def test_reports_undecodable_body(self) -> None:
        cloud = xiaomi.MiCloud(_token())
        cloud.session = MagicMock()
        cloud.session.post.return_value = FakeResponse("!!! not base64 !!!")

        with pytest.raises(xiaomi.XiaomiError):
            cloud._post("/x", {})

    def test_forwards_session_cookies(self) -> None:
        cloud = xiaomi.MiCloud(_token())
        fake = FakeSession(base64.b64decode(SSECURITY), {"code": 0})
        fake.cookies.get_dict.return_value = {"sid": "abc"}
        cloud.session = fake

        cloud._post("/x", {})

        assert fake.seen[0]["form"] is not None


class TestHost:
    def test_cn(self) -> None:
        assert xiaomi.MiCloud(_token()).host == "https://hlth.io.mi.com"

    def test_other_regions(self) -> None:
        assert xiaomi.MiCloud(_token(), region="de").host == "https://de.hlth.io.mi.com"


def _raw_item(seconds: float, value: dict, sid: str = "yunmai.scales.ms103") -> dict:
    return {"key": "weight", "time": int(seconds), "sid": sid, "value": json.dumps(value)}


class TestFetchWeightRecords:
    def _cloud(self, pages: list[dict]) -> xiaomi.MiCloud:
        cloud = xiaomi.MiCloud(_token())
        cloud._post = MagicMock(side_effect=pages)  # type: ignore[method-assign]
        return cloud

    def test_follows_pagination(self) -> None:
        cloud = self._cloud(
            [
                {"code": 0, "result": {"data_list": [_raw_item(1000, {"weight": 70.0})], "has_more": True, "next_key": "k2"}},
                {"code": 0, "result": {"data_list": [_raw_item(2000, {"weight": 71.0})], "has_more": False}},
            ]
        )

        records = cloud.fetch_weight_records()

        assert [r["weight_kg"] for r in records] == [70.0, 71.0]
        assert cloud._post.call_count == 2
        # The cursor has to be echoed back on the second page.
        assert cloud._post.call_args_list[1][0][1]["next_key"] == "k2"

    def test_sorts_oldest_first(self) -> None:
        cloud = self._cloud(
            [
                {
                    "code": 0,
                    "result": {
                        "data_list": [_raw_item(3000, {"weight": 72.0}), _raw_item(1000, {"weight": 70.0})],
                        "has_more": False,
                    },
                }
            ]
        )

        assert [r["weight_kg"] for r in cloud.fetch_weight_records()] == [70.0, 72.0]

    def test_reports_a_refusal(self) -> None:
        cloud = self._cloud([{"code": 401, "message": "bad token"}])

        with pytest.raises(xiaomi.XiaomiError, match="refused"):
            cloud.fetch_weight_records()

    def test_tolerates_a_missing_result_object(self) -> None:
        cloud = self._cloud([{"code": 0}])

        assert cloud.fetch_weight_records() == []


class TestNormalise:
    def test_reads_the_current_snake_case_layout(self) -> None:
        record = xiaomi._normalise(
            _raw_item(
                1700000000,
                {
                    "weight": 71.2,
                    "bmi": 22.9,
                    "body_fat_rate": 18.4,
                    "moisture_rate": 55.2,
                    "bone_mass": 3.1,
                    "muscle_rate": 40.0,
                    "visceral_fat": 8,
                    "basal_metabolism": 1600,
                    "ma": 36,
                },
            )
        )

        assert record is not None
        assert record["weight_kg"] == 71.2
        assert record["body_fat_pct"] == 18.4
        assert record["body_water_pct"] == 55.2
        assert record["bone_mass_kg"] == 3.1
        # muscle_rate is a percentage of body weight, not kilograms.
        assert record["muscle_mass_kg"] == round(0.40 * 71.2, 2)
        assert record["visceral_fat"] == 8
        assert record["basal_met"] == 1600
        assert record["metabolic_age"] == 36
        assert record["source"] == "yunmai.scales.ms103"

    def test_reads_the_legacy_abbreviated_layout(self) -> None:
        record = xiaomi._normalise(
            _raw_item(1700000000, {"weight": 71.2, "bfp": 18.4, "bwp": 55.2, "bmc": 3.1, "smm": 28.5})
        )

        assert record is not None
        assert record["body_fat_pct"] == 18.4
        assert record["body_water_pct"] == 55.2
        assert record["bone_mass_kg"] == 3.1
        # smm is already kilograms and must win over any computed value.
        assert record["muscle_mass_kg"] == 28.5

    def test_skips_other_metric_keys(self) -> None:
        assert xiaomi._normalise({"key": "steps", "time": 1, "value": "{}"}) is None

    def test_skips_unparseable_values(self) -> None:
        assert xiaomi._normalise({"key": "weight", "time": 1, "value": "{oops"}) is None

    def test_skips_records_without_a_weight(self) -> None:
        assert xiaomi._normalise(_raw_item(1700000000, {"bmi": 22.9})) is None

    def test_skips_non_dict_payloads(self) -> None:
        assert xiaomi._normalise({"key": "weight", "time": 1, "value": "[1,2]"}) is None

    def test_ignores_zero_and_negative_values(self) -> None:
        # Garmin and Xiaomi both use 0 as "not measured"; storing it would put a
        # 0 % body-fat point on the chart.
        record = xiaomi._normalise(_raw_item(1700000000, {"weight": 71.2, "body_fat_rate": 0, "bmi": -1}))

        assert record is not None
        assert "body_fat_pct" not in record
        assert "bmi" not in record

    def test_accepts_string_numbers(self) -> None:
        record = xiaomi._normalise(_raw_item(1700000000, {"weight": "71.2"}))

        assert record is not None
        assert record["weight_kg"] == 71.2

    def test_ignores_booleans(self) -> None:
        # True == 1 numerically, so without an explicit guard a stray flag would
        # become a 1 kg weight or a 1 % body fat reading.
        record = xiaomi._normalise(_raw_item(1700000000, {"weight": True}))

        assert record is None

    def test_timestamp_is_local_time(self) -> None:
        record = xiaomi._normalise(_raw_item(1700000000, {"weight": 70.0}))

        assert record is not None
        expected = datetime.fromtimestamp(1700000000)
        assert record["timestamp"] == expected.strftime("%Y-%m-%dT%H:%M:%S")
        assert record["date"] == expected.strftime("%Y-%m-%d")


class TestFetchWeights:
    def test_requires_a_token(self, monkeypatch) -> None:
        monkeypatch.setattr(xiaomi, "load_token", lambda: None)

        with pytest.raises(xiaomi.XiaomiError, match="garmin-mcp-lite-xiaomi-login"):
            xiaomi.fetch_weights()

    def test_refreshes_saves_and_filters_by_window(self, monkeypatch) -> None:
        saved: list[dict] = []
        now = datetime.now()
        records = [
            {"timestamp": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"), "date": "recent"},
            {"timestamp": (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S"), "date": "old"},
        ]

        monkeypatch.setattr(xiaomi, "load_token", _token)
        monkeypatch.setattr(xiaomi, "save_token", saved.append)
        monkeypatch.setattr(xiaomi.MiCloud, "refresh", lambda self: _token())
        monkeypatch.setattr(xiaomi.MiCloud, "fetch_weight_records", lambda self: records)

        result = xiaomi.fetch_weights(days=7)

        assert [record["date"] for record in result] == ["recent"]
        # The rotated token must be persisted, otherwise it expires unnoticed.
        assert saved == [_token()]

    def test_zero_days_still_means_one_day(self, monkeypatch) -> None:
        monkeypatch.setattr(xiaomi, "load_token", _token)
        monkeypatch.setattr(xiaomi, "save_token", lambda token: None)
        monkeypatch.setattr(xiaomi.MiCloud, "refresh", lambda self: _token())
        monkeypatch.setattr(xiaomi.MiCloud, "fetch_weight_records", lambda self: [])

        assert xiaomi.fetch_weights(days=0) == []


    def test_load_returns_none_when_the_json_is_not_an_object(self, tmp_dir, monkeypatch) -> None:
        path = tmp_dir / "xiaomi.json"
        path.write_text('["userId"]', encoding="utf-8")
        monkeypatch.setattr(xiaomi, "TOKEN_PATH", path)
        assert xiaomi.load_token() is None


class TestServiceLogin:
    """The only place the account password is put on the wire."""

    def _login(self) -> xiaomi.MiLogin:
        login = xiaomi.MiLogin()
        login.session = MagicMock()
        login.session.get.return_value = FakeResponse(
            '&&&START&&&{"sid":"miothealth","callback":"https://cb","_sign":"S","qs":"q"}'
        )
        return login

    def test_hashes_the_password_and_carries_the_session(self) -> None:
        login = self._login()
        login.session.post.return_value = FakeResponse('&&&START&&&{"code":0,"location":"https://loc"}')

        result = login._service_login("user@example.com", "hunter2")

        form = login.session.post.call_args[1]["data"]
        assert form["user"] == "user@example.com"
        # Xiaomi expects an uppercase MD5; the clear text must never be sent.
        assert form["hash"] == hashlib.md5(b"hunter2").hexdigest().upper()
        assert "hunter2" not in json.dumps(form)
        # The sid/callback/_sign/qs from the first GET must be echoed back, and
        # the device identity has to stay on the request cookies.
        assert form["sid"] == "miothealth"
        assert form["callback"] == "https://cb"
        assert form["_sign"] == "S"
        cookies = login.session.post.call_args[1]["cookies"]
        assert cookies["sdkVersion"] == xiaomi.SDK_VERSION
        assert cookies["deviceId"] == login.device_id
        assert result["location"] == "https://loc"

    def test_forwards_the_captcha_code_and_its_cookie(self) -> None:
        login = self._login()
        login._auth = {"ick": "the-ick"}
        login.session.post.return_value = FakeResponse('&&&START&&&{"code":0}')

        login._service_login("u", "p", captcha="abcd")

        form = login.session.post.call_args[1]["data"]
        assert form["captCode"] == "abcd"
        assert login.session.post.call_args[1]["cookies"]["ick"] == "the-ick"


class TestCookieDict:
    """`dict(jar)` raises CookieConflictError when a name repeats, which is
    exactly what a real 2FA login hit: Xiaomi sets `cUserId` on both the account
    domain and the sts callback domain."""

    def test_survives_a_name_present_on_two_domains(self) -> None:
        jar = RequestsCookieJar()
        jar.set("cUserId", "stale", domain=".xiaomi.com", path="/")
        jar.set("cUserId", "fresh", domain="sts-hlth.io.mi.com", path="/")
        jar.set("passToken", "pt", domain=".xiaomi.com", path="/")

        assert xiaomi._cookie_dict(jar) == {"cUserId": "stale", "passToken": "pt"}

    def test_prefers_the_callback_domain(self) -> None:
        jar = RequestsCookieJar()
        jar.set("cUserId", "stale", domain=".xiaomi.com", path="/")
        jar.set("cUserId", "fresh", domain="sts-hlth.io.mi.com", path="/")

        assert xiaomi._cookie_dict(jar, "sts-hlth.io.mi.com")["cUserId"] == "fresh"

    def test_falls_back_to_a_non_empty_value(self) -> None:
        jar = RequestsCookieJar()
        jar.set("token", "", domain=".xiaomi.com", path="/")
        jar.set("token", "real", domain=".xiaomi.com", path="/")

        assert xiaomi._cookie_dict(jar)["token"] == "real"

    def test_ignores_entries_without_a_name(self) -> None:
        nameless = [SimpleNamespace(name="", value="v", domain="d")]

        assert xiaomi._cookie_dict(nameless) == {}


class TestLogin:
    def _login(self) -> xiaomi.MiLogin:
        login = xiaomi.MiLogin()
        login.session = MagicMock()
        return login

    def test_captcha_loop_then_success(self) -> None:
        login = self._login()
        login._show_captcha = MagicMock(return_value=Path("/tmp/c.png"))
        login._service_login = MagicMock(
            side_effect=[
                {"captchaUrl": "/captcha?x=1"},
                {"location": "https://loc"},
            ]
        )
        login.session.get.return_value = FakeResponse("ok", headers={})
        login.session.get.return_value.cookies = _jar()
        login.session.get.return_value.history = []
        login._credentials = MagicMock(return_value=_token())

        shown: list[Path] = []
        assert login.login("u", "p", prompt=lambda _: "abcd", on_captcha=shown.append) == _token()
        assert login._service_login.call_count == 2
        assert login._service_login.call_args_list[1][1]["captcha"] == "abcd"
        # The image path has to reach the caller so it can be shown to the user.
        assert shown == [Path("/tmp/c.png")]

    def test_gives_up_after_three_captchas(self) -> None:
        login = self._login()
        login._show_captcha = MagicMock(return_value=Path("/tmp/c.png"))
        login._service_login = MagicMock(return_value={"captchaUrl": "/captcha"})

        with pytest.raises(xiaomi.XiaomiError, match="three times"):
            login.login("u", "p", prompt=lambda _: "wrong")

    def test_routes_to_two_factor(self) -> None:
        login = self._login()
        login._service_login = MagicMock(return_value={"notificationUrl": "https://n/fe/service/identity/authStart"})
        login._two_factor = MagicMock(return_value=_token())

        assert login.login("u", "p") == _token()
        login._two_factor.assert_called_once()

    def test_credentials_follow_the_redirect_chain(self) -> None:
        login = self._login()
        hop = MagicMock()
        hop.cookies = _jar()
        hop.headers = {"extension-pragma": json.dumps({"userId": "7", "passToken": "pt"})}
        final = FakeResponse("ok")
        final.cookies = _jar()
        final.history = [hop]
        login.session.get.return_value = final

        token = login._credentials({"location": "https://loc", "ssecurity": SSECURITY})

        assert token["userId"] == "7"
        assert token["passToken"] == "pt"

    def test_reports_xiaomis_rejection_code_not_a_missing_field(self) -> None:
        # A rejected password returns `location: ""` alongside `code: 70016`, so
        # the old message blamed a missing field while the answer was right there.
        login = self._login()
        login._service_login = MagicMock(
            return_value={
                "code": 70016,
                "description": "登录验证失败",
                "location": "",
                "captchaUrl": None,
                "callback": "https://sts-hlth.io.mi.com/healthapp/sts",
            }
        )

        with pytest.raises(xiaomi.XiaomiError, match="code 70016.*登录验证失败"):
            login.login("user@example.com", "wrong-password", prompt=lambda _: "")

    def test_credentials_survive_duplicate_cookie_names(self) -> None:
        # Regression: the first real 2FA login died on dict(hop.cookies) because
        # Xiaomi sets cUserId on two domains at once.
        login = self._login()
        jar = RequestsCookieJar()
        jar.set("cUserId", "stale", domain=".xiaomi.com", path="/")
        jar.set("cUserId", "fresh", domain="sts-hlth.io.mi.com", path="/")
        final = FakeResponse("ok")
        final.cookies = jar
        final.history = []
        login.session.get.return_value = final

        token = login._credentials(
            {
                "location": "https://sts-hlth.io.mi.com/healthapp/sts",
                "ssecurity": SSECURITY,
                "userId": "42",
                "passToken": "pt",
            }
        )

        assert token["userId"] == "42"
        assert token["passToken"] == "pt"

    def test_credentials_require_a_location(self) -> None:
        login = self._login()

        with pytest.raises(xiaomi.XiaomiError, match="no usable location"):
            login._credentials({"code": 0})

    def test_credentials_require_ssecurity(self) -> None:
        login = self._login()
        final = FakeResponse("ok")
        final.cookies = _jar()
        final.history = []
        login.session.get.return_value = final

        with pytest.raises(xiaomi.XiaomiError, match="no ssecurity"):
            login._credentials({"location": "https://loc"})

    def test_two_factor_uses_the_phone_flow(self) -> None:
        login = self._login()
        listing = FakeResponse('&&&START&&&{"flag":4}')
        listing.cookies = _jar(identity_session="sess")
        verify = FakeResponse('&&&START&&&{"maskedPhone":"138****0000"}')
        sent = FakeResponse('&&&START&&&{"code":0}')
        login.session.get.side_effect = [listing, verify]
        login.session.post.return_value = sent
        login._credentials = MagicMock(return_value=_token())

        token = login._two_factor("https://n/fe/service/identity/authStart", prompt=lambda _: "123456")

        assert token == _token()
        # sendPhoneTicket, not sendEmailTicket.
        assert "sendPhoneTicket" in login.session.post.call_args_list[0][0][0]

    def test_two_factor_reports_a_missing_session_cookie(self) -> None:
        login = self._login()
        listing = FakeResponse('&&&START&&&{"flag":4}')
        listing.cookies = _jar()
        login.session.get.return_value = listing

        with pytest.raises(xiaomi.XiaomiError, match="identity_session"):
            login._two_factor("https://n/fe/service/identity/authStart", prompt=lambda _: "1")

    def test_show_captcha_writes_the_image(self, tmp_dir, monkeypatch) -> None:
        login = self._login()
        login.session.get.return_value = FakeResponse("png-bytes")
        login.session.get.return_value.cookies = {"ick": "the-ick"}
        target = tmp_dir / "captcha.png"
        monkeypatch.setattr(xiaomi, "CAPTCHA_PATH", target)

        path = login._show_captcha("/captcha?x=1")

        assert path == target
        assert target.read_text(encoding="utf-8") == "png-bytes"
        # The ick cookie has to be carried into the retry, or the second
        # serviceLoginAuth2 call is rejected even with the right code.
        assert login._auth["ick"] == "the-ick"

    def test_device_id_is_sixteen_chars(self) -> None:
        assert len(xiaomi._device_id()) == 16
