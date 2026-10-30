import time
from datetime import UTC, datetime
from typing import Any

from garmin_mcp_lite.client import get_client
from garmin_mcp_lite.tools._common import as_dict, as_list, days_ago_str, today_str

# Garmin reports every mass field in this payload in grams (69800.0 means 69.8 kg),
# while every write path and every human means kilograms. Anything above this
# threshold can only be grams — bone mass is a few kg, muscle mass a few tens —
# so a single rule normalises weight, muscle mass and bone mass at once.
_GRAM_THRESHOLD = 500.0
_GRAMS_PER_KG = 1000.0

# A body-composition entry is a point measurement, so the useful window is short.
_MAX_DAYS = 730

# garminconnect writes a float into a FIT field that holds hundredths, truncating
# rather than rounding, so 72.8 would be stored as 72.79. Padding by a hair makes
# the truncation land on the number the user actually weighed.
_FIT_HEADROOM = 1e-6

# Garmin answers 429 when writes arrive too fast. garminconnect retries 5xx and
# network errors itself but hands a 429 straight back — "caller actionable" — so
# the waiting is this module's job. Three tries, doubling, capped so a hostile
# Retry-After header cannot hang a tool call.
_RATE_LIMIT_ATTEMPTS = 3
_RATE_LIMIT_WAIT_S = 2.0
_RATE_LIMIT_MAX_WAIT_S = 30.0


def _to_kg(value: Any) -> float | None:
    """Normalise one Garmin mass field to kilograms, or None when absent."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    if value > _GRAM_THRESHOLD:
        return round(value / _GRAMS_PER_KG, 2)
    return round(float(value), 2)


def _record(row: dict) -> dict[str, Any]:
    """Flatten one body-composition row, dropping the fields Garmin left null."""
    record: dict[str, Any] = {}
    date = row.get("calendarDate")
    if date:
        record["date"] = date

    for source, target in (
        ("weight", "weight_kg"),
        ("muscleMass", "muscle_mass_kg"),
        ("boneMass", "bone_mass_kg"),
    ):
        value = _to_kg(row.get(source))
        if value is not None:
            record[target] = value

    for source, target in (
        ("bmi", "bmi"),
        ("bodyFat", "body_fat_pct"),
        ("bodyWater", "body_water_pct"),
        ("visceralFat", "visceral_fat"),
        ("metabolicAge", "metabolic_age"),
        ("physiqueRating", "physique_rating"),
    ):
        value = row.get(source)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            record[target] = value

    source_type = row.get("sourceType")
    if source_type:
        record["source"] = source_type
    return record


def _average(payload: dict) -> dict[str, Any]:
    raw = as_dict(payload.get("totalAverage"))
    average: dict[str, Any] = {}
    weight = _to_kg(raw.get("weight"))
    if weight is not None:
        average["weight_kg"] = weight
    for source, target in (("bmi", "bmi"), ("bodyFat", "body_fat_pct"), ("bodyWater", "body_water_pct")):
        value = raw.get(source)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            average[target] = round(float(value), 2)
    return average


def get_body_composition(days: int = 90, limit: int = 60) -> dict:
    """Read weight and body-composition history from Garmin Connect.

    Use this before `garmin_add_body_composition` to see whether a day already
    has an entry, and to answer trend questions ("did my body fat move").

    Mass fields are converted to kilograms and null fields are omitted, so a
    record only carries the metrics that were actually measured. Most accounts
    only ever have `weight_kg`, because a scale that syncs weight alone (e.g.
    MyFitnessPal) never populates body fat, muscle mass or BMI.

    Args:
        days: How many days back to look. Defaults to 90, capped at 730.
        limit: Maximum number of records to return, newest first. Defaults to 60.
    """
    window = max(1, min(int(days), _MAX_DAYS))
    start = days_ago_str(window)
    end = today_str()

    try:
        payload = as_dict(get_client().get_body_composition(start, end))
    except Exception as e:
        return {"error": str(e)}

    rows = [row for row in as_list(payload.get("dateWeightList")) if isinstance(row, dict)]
    records = [record for record in (_record(row) for row in rows) if record]
    records.sort(key=lambda item: str(item.get("date") or ""), reverse=True)

    result: dict[str, Any] = {
        "range": {"start": start, "end": end},
        "count": len(records),
        "records": records[: max(1, int(limit))],
    }

    if records:
        result["latest"] = records[0]
        average = _average(payload)
        if average:
            result["average"] = average

        # Oldest vs newest inside the window: the single number people ask for.
        weights = [
            (str(item["date"]), item["weight_kg"])
            for item in records
            if isinstance(item.get("weight_kg"), (int, float))
        ]
        if len(weights) >= 2:
            (oldest_date, oldest_weight), (newest_date, newest_weight) = weights[-1], weights[0]
            result["change"] = {
                "weight_kg": round(float(newest_weight) - float(oldest_weight), 2),
                "from": oldest_date,
                "to": newest_date,
            }
    else:
        result["latest"] = None

    return result


def _validate_weight(weight: float) -> float:
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise ValueError(f"weight must be a number in kilograms, got {weight!r}")
    value = float(weight)
    if value <= 0:
        raise ValueError("weight must be positive")
    if value > _GRAM_THRESHOLD:
        # The read path returns grams, so a read-modify-write is the obvious way
        # to end up here. Say so instead of writing a 69 800 kg weigh-in.
        raise ValueError(
            f"weight={value} looks like grams, not kilograms. Pass kilograms (70.5), not grams (70500)."
        )
    return value


def _fit_scaled(value: float) -> float:
    """Pad a value so garminconnect's FIT encoder truncates to it, not below it."""
    return round(float(value), 2) + _FIT_HEADROOM


def _fit_optional(value: float | None) -> float | None:
    return None if value is None else _fit_scaled(value)


def _resolve_timestamp(date: str | None) -> str:
    if not date:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    text = str(date).strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"date must be YYYY-MM-DD or ISO 8601, got {date!r}") from exc
    # A bare date carries no time of day. Weigh-ins happen in the morning, and
    # midnight can land on the previous day once Garmin applies a timezone.
    if len(text) == 10:
        parsed = parsed.replace(hour=7, minute=0, second=0)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


def _existing_on(client: Any, day: str) -> dict[str, Any] | None:
    """Return the weight already recorded on `day`, if any."""
    try:
        payload = as_dict(client.get_body_composition(day, day))
    except Exception:
        return None
    for row in as_list(payload.get("dateWeightList")):
        if isinstance(row, dict):
            weight = _to_kg(row.get("weight"))
            if weight is not None:
                return {"weight_kg": weight, "source": row.get("sourceType")}
    return None


def _ms(value: Any) -> float | None:
    """A millisecond timestamp field as seconds, or None when unusable."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value) / 1000.0


def _row_offset(row: dict[str, Any]) -> float | None:
    """The account's zone offset this row proves, in seconds.

    Garmin reports each weigh-in twice: `date` is the wall clock in the account's
    display zone, `timestampGMT` the true instant. Their difference *is* the zone,
    which is what makes every write self-calibrating instead of one more setting
    to get wrong. Measured on a China account: exactly 28,800,000 ms apart.
    """
    wall, instant = _ms(row.get("date")), _ms(row.get("timestampGMT"))
    if wall is None or instant is None:
        return None
    return wall - instant


def _day_state(client: Any, day: str) -> dict[str, Any]:
    """What Garmin holds on `day`: the entry already there, and its zone offset."""
    try:
        payload = as_dict(client.get_body_composition(day, day))
    except Exception:
        return {}
    state: dict[str, Any] = {}
    offsets: list[float] = []
    for row in as_list(payload.get("dateWeightList")):
        if not isinstance(row, dict):
            continue
        offset = _row_offset(row)
        if offset is not None:
            offsets.append(offset)
        if "existing" not in state:
            weight = _to_kg(row.get("weight"))
            if weight is not None:
                state["existing"] = {"weight_kg": weight, "source": row.get("sourceType")}
    if offsets:
        state["offset_s"] = sorted(offsets)[len(offsets) // 2]
    return state


def _account_offset(client: Any, start: str, end: str) -> float | None:
    """The account's zone, read off every row in a window, in seconds.

    A single day proves nothing when it is empty, and one row that arrived by some
    other route should not decide where every weighing lands, so the median over
    the window is used. None when the window holds no usable pair — the caller
    then leaves the timestamp alone rather than guessing at a shift.
    """
    try:
        payload = as_dict(client.get_body_composition(start, end))
    except Exception:
        return None
    offsets = [
        offset
        for row in as_list(payload.get("dateWeightList"))
        if isinstance(row, dict) and (offset := _row_offset(row)) is not None
    ]
    return sorted(offsets)[len(offsets) // 2] if offsets else None


def _sendable(timestamp: str, offset_s: float | None) -> str:
    """The date string that makes Garmin store `timestamp` as the wall clock.

    garminconnect builds the FIT file with `time.mktime(dt.timetuple())`, which
    reads a naive datetime as the *machine's* local time, and Garmin then renders
    that instant in the *account's* display zone. The two agree only while the
    machine sits in the account's zone — measured on the live account: the same
    07:30 sent from a laptop in New York came back as 19:30, twelve hours off,
    after which it no longer matched the scale and was written a second time.

    So what goes out is the instant, expressed in whatever zone this machine is
    in. With a matching zone the string is the timestamp itself, and with no zone
    known — `offset_s` is None — it is left alone rather than guessed at.
    """
    if not offset_s:
        return timestamp
    wall = datetime.fromisoformat(timestamp)
    instant = wall.replace(tzinfo=UTC).timestamp() - offset_s
    return datetime.fromtimestamp(instant).isoformat()


def _upload_status(raw: Any) -> str | None:
    """Pull the per-file status out of Garmin's FIT import response."""
    import_result = as_dict(as_dict(raw).get("detailedImportResult"))
    for upload in as_list(import_result.get("uploads")):
        if isinstance(upload, dict) and upload.get("status"):
            return str(upload["status"])
    return None


def _chain(exc: BaseException) -> list[BaseException]:
    """`exc` and every error it was raised from, outermost first."""
    links: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and not any(current is link for link in links):
        links.append(current)
        current = current.__cause__ or current.__context__
    return links


def _rate_limited(exc: BaseException) -> bool:
    """Whether Garmin refused this request for going too fast.

    garminconnect 0.3 raises a dedicated error for it but attaches no response,
    and the HTTP error it wraps still carries the status — so both the type name
    and the status code are checked, which also covers the older releases that
    let the raw HTTP error through.
    """
    for link in _chain(exc):
        if type(link).__name__ == "GarminConnectTooManyRequestsError":
            return True
        if getattr(getattr(link, "response", None), "status_code", None) == 429:
            return True
    return False


def _retry_after(exc: BaseException) -> float | None:
    """The wait Garmin asked for, when it bothered to say."""
    for link in _chain(exc):
        headers = getattr(getattr(link, "response", None), "headers", None)
        if not headers:
            continue
        header = headers.get("Retry-After")
        if header is None:
            continue
        try:
            return float(header)
        except ValueError:  # an HTTP-date, or a proxy's idea of a joke
            continue
    return None


def _upload(client: Any, **fields: Any) -> Any:
    """Upload one FIT file, waiting out a rate limit instead of dropping the write.

    A 429 is the one failure garminconnect declines to retry — it hands it back as
    "caller actionable" — and the one failure a bulk backfill provokes. This is
    that caller. A timeout is deliberately *not* retried here: it may have landed,
    and a duplicate weighing is worse than a gap the next sync fills by itself.
    """
    attempt = 0
    while True:
        try:
            return client.add_body_composition(**fields)
        except Exception as exc:
            attempt += 1
            if attempt >= _RATE_LIMIT_ATTEMPTS or not _rate_limited(exc):
                raise
            wait = _retry_after(exc) or _RATE_LIMIT_WAIT_S * 2 ** (attempt - 1)
            time.sleep(min(wait, _RATE_LIMIT_MAX_WAIT_S))


def add_body_composition(
    weight: float,
    date: str | None = None,
    body_fat: float | None = None,
    body_water: float | None = None,
    muscle_mass: float | None = None,
    bone_mass: float | None = None,
    bmi: float | None = None,
    basal_met: float | None = None,
    metabolic_age: int | None = None,
) -> dict:
    """Write one weight / body-composition measurement to Garmin Connect.

    THIS WRITES TO YOUR GARMIN ACCOUNT. Garmin stores it as a FIT body-composition
    file, the same channel its own Index scale uses, so the entry shows up in the
    Garmin Connect app's weight chart. Confirm the numbers with the user before
    calling this: there is no undo through this tool.

    Garmin keeps every entry, so calling twice for the same day can leave two
    weigh-ins. The response includes a `warning` when the day already had one.

    Args:
        weight: Body weight in KILOGRAMS (e.g. 70.5). Values above 500 are
                rejected as an accidental gram value.
        date: When the measurement was taken. `YYYY-MM-DD` (recorded at 07:00
              local) or a full ISO 8601 timestamp. Defaults to now.
        body_fat: Body fat percentage, e.g. 18.5.
        body_water: Body water percentage, e.g. 55.2.
        muscle_mass: Muscle mass in kilograms.
        bone_mass: Bone mass in kilograms.
        bmi: Body mass index. Garmin derives this from your profile height when
             omitted, so leave it out unless you have a reason to override it.
        basal_met: Basal metabolic rate in kcal/day.
        metabolic_age: Metabolic age in years.
    """
    return _write_composition(
        get_client(),
        value=_validate_weight(weight),
        timestamp=_resolve_timestamp(date),
        body_fat=body_fat,
        body_water=body_water,
        muscle_mass=muscle_mass,
        bone_mass=bone_mass,
        bmi=bmi,
        basal_met=basal_met,
        metabolic_age=metabolic_age,
        account_offset_s=None,
    )


def _write_composition(
    client: Any,
    *,
    value: float,
    timestamp: str,
    body_fat: float | None = None,
    body_water: float | None = None,
    muscle_mass: float | None = None,
    bone_mass: float | None = None,
    bmi: float | None = None,
    basal_met: float | None = None,
    metabolic_age: int | None = None,
    account_offset_s: float | None = None,
) -> dict:
    """Upload one measurement and report what Garmin did with it.

    Split out from `add_body_composition` so the sync can pass an account zone it
    calibrated from a whole window; the public tool has no such thing to give and
    leaves it to be read off the day's own rows. `day` and the echoed `timestamp`
    are always the wall clock the caller meant — only the FIT file carries the
    translated instant.
    """
    day = timestamp[:10]

    # add_body_composition() is absent from the oldest garminconnect releases this
    # package still allows, and would otherwise surface as an opaque AttributeError.
    if not callable(getattr(client, "add_body_composition", None)):
        return {
            "error": "This garminconnect version cannot write body composition. Upgrade to garminconnect>=0.3.0.",
            "written": False,
        }

    state = _day_state(client, day)
    existing = state.get("existing")
    offset_s = account_offset_s if account_offset_s is not None else state.get("offset_s")

    try:
        raw = _upload(
            client,
            timestamp=_sendable(timestamp, offset_s),
            weight=_fit_scaled(value),
            percent_fat=_fit_optional(body_fat),
            percent_hydration=_fit_optional(body_water),
            muscle_mass=_fit_optional(muscle_mass),
            bone_mass=_fit_optional(bone_mass),
            bmi=_fit_optional(bmi),
            basal_met=basal_met,
            metabolic_age=metabolic_age,
        )
    except Exception as e:
        error: dict[str, Any] = {"error": str(e), "written": False}
        if _rate_limited(e):
            # The caller needs to tell "this one write failed" apart from "Garmin
            # is refusing everything now", or it will hammer the remaining queue.
            error["rate_limited"] = True
        return error

    result: dict[str, Any] = {"written": True, "date": day, "timestamp": timestamp, "weight_kg": value}
    for key, field_value in (
        ("body_fat_pct", body_fat),
        ("body_water_pct", body_water),
        ("muscle_mass_kg", muscle_mass),
        ("bone_mass_kg", bone_mass),
        ("bmi", bmi),
        ("basal_met", basal_met),
        ("metabolic_age", metabolic_age),
    ):
        if field_value is not None:
            result[key] = field_value

    status = _upload_status(raw)
    if status:
        result["garmin_status"] = status
    else:
        # Garmin's upload endpoint answers with a body whose shape varies by
        # account and API version — sometimes empty, sometimes without
        # `detailedImportResult` — so a missing status proves nothing either way.
        # Reading the day back is the only reliable confirmation, and it is what
        # caught this during live testing.
        stored = _existing_on(client, day)
        result["verified"] = stored is not None and abs(float(stored["weight_kg"]) - value) < 0.2
        if stored:
            result["stored"] = stored

    if existing:
        result["warning"] = (
            f"{day} already had {existing['weight_kg']} kg"
            f" (source {existing['source'] or 'unknown'}); Garmin may now show both entries."
        )
    return result
