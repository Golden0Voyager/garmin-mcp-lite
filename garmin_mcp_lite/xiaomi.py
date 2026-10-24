"""Read-only client for the Mi Fitness cloud (小米运动健康).

Xiaomi documents none of this. The request signature is their private protocol:
a per-request key is ``sha256(ssecurity + nonce)``, where the nonce is 8 random
bytes followed by the current time in minutes as a big-endian uint32. The JSON
body is RC4-encrypted with that key, and two SHA1 hashes bind the plaintext, the
ciphertext and the URI together. Responses are RC4-encrypted the same way. The
scheme is reimplemented here (rather than imported) so this package needs
nothing beyond ``requests``.

Two things bite:

* The nonce embeds a minute-resolution clock, so a host clock that is off by
  more than a minute fails every request. ``MiCloud.refresh()`` records the
  offset between the local clock and Xiaomi's ``Date`` header and every
  subsequent request applies it.
* There is no incremental sync. The endpoint pages through everything the
  account has; filtering by date happens on our side.

Only the read path lives here. Writing to Garmin stays in
``garmin_mcp_lite.tools.body``, which already knows how to confirm a write.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import string
import struct
import time
from datetime import datetime, timedelta
from email.utils import mktime_tz, parsedate_tz
from pathlib import Path
from typing import Any

import requests

SID = "miothealth"
SDK_VERSION = "4.2.29"
USER_AGENT = "MisFit/2.0.0 (iPhone; iOS 13.0; Scale/2.0.0)"
ACCOUNT_URL = "https://account.xiaomi.com"

# Same directory as the Garmin token, so uninstalling means deleting one folder.
TOKEN_PATH = Path(os.environ.get("GARMIN_TOKEN_DIR", "~/.garmin-mcp-lite")).expanduser() / "xiaomi.json"

# Where the captcha image is dropped for the user to read. Kept as a module
# constant so tests do not have to write into /tmp.
CAPTCHA_PATH = Path("/tmp/xiaomi_captcha.png")

FLAG_PHONE = 4


class XiaomiError(RuntimeError):
    """Raised when the Mi cloud refuses a login or a request."""


def _parse_auth(body: bytes) -> dict[str, Any]:
    """Xiaomi prefixes JSON auth responses with a fixed marker."""
    text = body.decode("utf-8", errors="replace")
    marker = "&&&START&&&"
    if text.startswith(marker):
        text = text[len(marker) :]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise XiaomiError(f"Unexpected response from Xiaomi: {text[:200]}") from exc


def _device_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def _rc4(key: bytes, data: bytes) -> bytes:
    """RC4 with the 1024-byte warm-up Xiaomi's own clients perform."""
    box = list(range(256))
    j = 0
    for i in range(256):
        j = (j + box[i] + key[i % len(key)]) % 256
        box[i], box[j] = box[j], box[i]

    i = j = 0
    for _ in range(1024):
        i = (i + 1) % 256
        j = (j + box[i]) % 256
        box[i], box[j] = box[j], box[i]

    out = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + box[i]) % 256
        box[i], box[j] = box[j], box[i]
        out.append(byte ^ box[(box[i] + box[j]) % 256])
    return bytes(out)


def load_token() -> dict[str, str] | None:
    """Read the cached token, or None when the user has never logged in."""
    try:
        raw = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    token = {key: str(raw.get(key) or "") for key in ("userId", "passToken", "ssecurity")}
    return token if all(token.values()) else None


def save_token(token: dict[str, str]) -> Path:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(token, indent=2), encoding="utf-8")
    # The file holds a password-equivalent bearer token.
    TOKEN_PATH.chmod(0o600)
    return TOKEN_PATH


class MiLogin:
    """Interactive account login, including captcha and SMS/email 2FA.

    Kept in the package rather than in a script because it is the only way to
    obtain the token that ``MiCloud`` needs, and it must stay in sync with the
    signing code when Xiaomi changes the protocol.
    """

    def __init__(self) -> None:
        self.session = requests.Session()
        self.device_id = _device_id()
        self.ssecurity = b""
        self._auth: dict[str, Any] = {}

    def _service_login(self, username: str, password: str, captcha: str | None = None) -> dict[str, Any]:
        r = self.session.get(
            f"{ACCOUNT_URL}/pass/serviceLogin",
            cookies={"sdkVersion": SDK_VERSION, "deviceId": self.device_id},
            params={"_json": "true", "sid": SID},
            timeout=30,
        )
        first = _parse_auth(r.content)

        cookies = {"sdkVersion": SDK_VERSION, "deviceId": self.device_id}
        data = {
            "_json": "true",
            "sid": first["sid"],
            "callback": first["callback"],
            "_sign": first["_sign"],
            "qs": first["qs"],
            "user": username,
            "hash": hashlib.md5(password.encode()).hexdigest().upper(),
        }
        if captcha:
            cookies["ick"] = self._auth["ick"]
            data["captCode"] = captcha

        r = self.session.post(f"{ACCOUNT_URL}/pass/serviceLoginAuth2", cookies=cookies, data=data, timeout=30)
        return _parse_auth(r.content)

    def _show_captcha(self, url: str) -> Path:
        r = self.session.get(ACCOUNT_URL + url, timeout=30)
        CAPTCHA_PATH.write_bytes(r.content)
        self._auth["ick"] = r.cookies["ick"]
        return CAPTCHA_PATH

    def _credentials(self, payload: dict[str, Any]) -> dict[str, str]:
        location = payload.get("location")
        if not location:
            # An empty string is what a rejected login returns, so this branch is
            # reached with a body that already explains itself.
            code = payload.get("code")
            if isinstance(code, int) and code != 0:
                raise XiaomiError(
                    f"Xiaomi rejected the login (code {code}: "
                    f"{payload.get('description') or payload.get('desc') or 'no reason given'}). "
                    "This is a credential rejection, not a network problem."
                )
            raise XiaomiError(f"Login response has no usable location: {payload}")

        r = self.session.get(location, timeout=30)
        merged = dict(payload)
        # userId / passToken arrive on any hop of the redirect chain, either as
        # a cookie or inside the extension-pragma header.
        for hop in r.history:
            merged.update(dict(hop.cookies))
            if pragma := hop.headers.get("extension-pragma"):
                merged.update(json.loads(pragma))
        merged.update(dict(r.cookies))

        if not merged.get("ssecurity"):
            raise XiaomiError(f"Login response has no ssecurity; got keys {sorted(merged)}")

        self.ssecurity = base64.b64decode(merged["ssecurity"])
        return {
            "userId": str(merged["userId"]),
            "passToken": str(merged["passToken"]),
            "ssecurity": base64.b64encode(self.ssecurity).decode(),
        }

    def _two_factor(self, notification_url: str, prompt: Any) -> dict[str, str]:
        url = notification_url.replace("/fe/service/identity/authStart", "/identity/list")
        r = self.session.get(url, timeout=30)
        flag = _parse_auth(r.content)["flag"]
        key = "Phone" if flag == FLAG_PHONE else "Email"
        session_id = r.cookies["identity_session"]

        r = self.session.get(
            f"{ACCOUNT_URL}/identity/auth/verify{key}",
            cookies={"identity_session": session_id},
            params={"_flag": flag, "_json": "true"},
            timeout=30,
        )
        masked = _parse_auth(r.content).get(f"masked{key}", "your phone/email")

        self.session.post(
            f"{ACCOUNT_URL}/identity/auth/send{key}Ticket",
            cookies={"identity_session": session_id},
            data={"retry": 0, "icode": "", "_json": "true"},
            timeout=30,
        )

        code = prompt(f"Verification code sent to {masked}: ").strip()
        r = self.session.post(
            f"{ACCOUNT_URL}/identity/auth/verify{key}",
            cookies={"identity_session": session_id},
            params={"_flag": flag, "ticket": code, "trust": "false", "_json": "true"},
            timeout=30,
        )
        return self._credentials(_parse_auth(r.content))

    def login(
        self,
        username: str,
        password: str,
        prompt: Any = input,
        on_captcha: Any = None,
    ) -> dict[str, str]:
        """Log in and return a token. `on_captcha(path)` is called when a code is needed."""
        result = self._service_login(username, password)
        for _ in range(3):
            captcha_url = result.get("captchaUrl")
            if not captcha_url:
                break
            path = self._show_captcha(captcha_url)
            if on_captcha is not None:
                on_captcha(path)
            code = prompt("Captcha code: ").strip()
            result = self._service_login(username, password, captcha=code)
        else:
            raise XiaomiError("Captcha failed three times; wait a few minutes and retry.")

        if notification_url := result.get("notificationUrl"):
            return self._two_factor(notification_url, prompt)
        return self._credentials(result)


class MiCloud:
    """Signed requests against the Mi Fitness health cloud."""

    def __init__(self, token: dict[str, str], region: str = "cn") -> None:
        self.token = dict(token)
        self.region = region
        self.session = requests.Session()
        self.time_offset = 0.0

    @property
    def _ssecurity(self) -> bytes:
        return base64.b64decode(self.token["ssecurity"])

    @property
    def host(self) -> str:
        return "https://hlth.io.mi.com" if self.region == "cn" else f"https://{self.region}.hlth.io.mi.com"

    def refresh(self) -> dict[str, str]:
        """Validate the token, rotate it, and sync the clock offset.

        Raises XiaomiError when the token has expired, which is the only signal
        that a human has to run the login command again.
        """
        r = self.session.get(
            f"{ACCOUNT_URL}/pass/serviceLogin?_json=true&sid={SID}",
            headers={
                "Cookie": f"userId={self.token['userId']}; passToken={self.token['passToken']}",
                "User-Agent": USER_AGENT,
            },
            timeout=30,
        )
        data = _parse_auth(r.content)
        if data.get("code") != 0:
            raise XiaomiError(
                "Mi Fitness token is no longer valid (password changed, security check, or "
                f"long inactivity). Run `garmin-mcp-lite-xiaomi-login` again. Detail: {data}"
            )

        if data.get("ssecurity"):
            self.token["ssecurity"] = base64.b64encode(base64.b64decode(data["ssecurity"])).decode()
        if data.get("userId"):
            self.token["userId"] = str(data["userId"])
        if data.get("passToken"):
            self.token["passToken"] = str(data["passToken"])

        if location := data.get("location"):
            r2 = self.session.get(location, timeout=30)
            if server_date := r2.headers.get("Date"):
                parsed = parsedate_tz(server_date)
                if parsed:
                    self.time_offset = mktime_tz(parsed) - time.time()
        return self.token

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        nonce = os.urandom(8) + struct.pack(">I", int((time.time() + self.time_offset) / 60))
        signed = hashlib.sha256(self._ssecurity + nonce).digest()
        signed_b64 = base64.b64encode(signed).decode()

        body = json.dumps(payload, separators=(",", ":"))
        rc4_hash = base64.b64encode(
            hashlib.sha1(f"POST&{path}&data={body}&{signed_b64}".encode()).digest()
        ).decode()
        enc_body = base64.b64encode(_rc4(signed, body.encode())).decode()
        enc_hash = base64.b64encode(_rc4(signed, rc4_hash.encode())).decode()
        signature = base64.b64encode(
            hashlib.sha1(f"POST&{path}&data={enc_body}&rc4_hash__={enc_hash}&{signed_b64}".encode()).digest()
        ).decode()

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookies := self.session.cookies.get_dict():
            headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())

        r = self.session.post(
            self.host + path,
            data={
                "data": enc_body,
                "rc4_hash__": enc_hash,
                "signature": signature,
                "_nonce": base64.b64encode(nonce).decode(),
            },
            headers=headers,
            timeout=30,
        )
        if r.status_code != 200:
            raise XiaomiError(f"Mi cloud returned HTTP {r.status_code}: {r.text[:200]}")

        try:
            return json.loads(_rc4(signed, base64.b64decode(r.text)))
        except Exception:
            # Error responses come back in plain JSON rather than encrypted.
            try:
                return json.loads(r.text)
            except json.JSONDecodeError as exc:
                raise XiaomiError(f"Cannot decode Mi cloud response: {r.text[:200]}") from exc

    def fetch_weight_records(self) -> list[dict[str, Any]]:
        """Page through every weight entry the account holds, oldest first."""
        items: list[dict[str, Any]] = []
        next_key: str | None = None

        while True:
            payload: dict[str, Any] = {"start_time": 1, "end_time": int(time.time()) + 86400, "key": "weight"}
            if next_key:
                payload["next_key"] = next_key

            data = self._post("/app/v1/data/get_fitness_data_by_time", payload)
            if not isinstance(data, dict) or data.get("code") != 0:
                raise XiaomiError(f"Mi cloud refused the weight query: {data}")

            result = data.get("result") or {}
            items.extend(result.get("data_list") or [])
            if not result.get("has_more") or not result.get("next_key"):
                break
            next_key = str(result["next_key"])

        records = [record for record in (_normalise(item) for item in items) if record]
        records.sort(key=lambda record: record["timestamp"])
        return records


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _normalise(item: dict[str, Any]) -> dict[str, Any] | None:
    """Flatten one Mi Fitness weight entry into the shape the sync tool needs.

    Xiaomi has shipped three payload layouts over the years (sourceType 1, 2 and
    3), and the newer endpoint uses snake_case keys while the older one used
    abbreviations. Both spellings are accepted here.
    """
    if item.get("key") != "weight":
        return None
    try:
        value = json.loads(item.get("value") or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None

    weight = _number(value.get("weight"))
    if weight is None:
        return None

    moment = datetime.fromtimestamp(int(item.get("time") or 0))
    record: dict[str, Any] = {
        "timestamp": moment.strftime("%Y-%m-%dT%H:%M:%S"),
        "date": moment.strftime("%Y-%m-%d"),
        "weight_kg": round(weight, 2),
        "source": item.get("sid") or "unknown",
    }

    # Muscle mass is reported as a percentage of body weight by the current API
    # and as kilograms (smm) by the legacy one.
    muscle_kg = _number(value.get("smm") or value.get("muscle_mass"))
    if muscle_kg is None:
        rate = _number(value.get("muscle_rate"))
        if rate is not None:
            muscle_kg = rate / 100 * weight
    if muscle_kg is not None:
        record["muscle_mass_kg"] = round(muscle_kg, 2)

    for source, target in (
        ("body_fat_rate", "body_fat_pct"),
        ("bfp", "body_fat_pct"),
        ("moisture_rate", "body_water_pct"),
        ("bwp", "body_water_pct"),
        ("bone_mass", "bone_mass_kg"),
        ("bmc", "bone_mass_kg"),
        ("bmi", "bmi"),
        ("visceral_fat", "visceral_fat"),
        ("vfl", "visceral_fat"),
        ("basal_metabolism", "basal_met"),
        ("bmr", "basal_met"),
        ("ma", "metabolic_age"),
    ):
        if target in record:
            continue
        number = _number(value.get(source))
        if number is not None:
            record[target] = round(number, 2) if target.endswith("_pct") else number
    return record


def fetch_weights(days: int = 7) -> list[dict[str, Any]]:
    """Return one normalised record per weigh-in inside the last `days` days.

    Raises XiaomiError with an actionable message when there is no token or the
    token has expired — both need a human, so the tool reports rather than
    retries.
    """
    token = load_token()
    if token is None:
        raise XiaomiError(
            f"No Mi Fitness token at {TOKEN_PATH}. Run `garmin-mcp-lite-xiaomi-login` once: "
            "logging in needs a captcha and possibly an SMS code, so it cannot happen from a tool call."
        )

    cloud = MiCloud(token)
    save_token(cloud.refresh())

    cutoff = datetime.now() - timedelta(days=max(1, int(days)))
    return [record for record in cloud.fetch_weight_records() if datetime.fromisoformat(record["timestamp"]) >= cutoff]
