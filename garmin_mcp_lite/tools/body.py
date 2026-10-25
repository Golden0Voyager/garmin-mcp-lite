from datetime import datetime
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


def _upload_status(raw: Any) -> str | None:
    """Pull the per-file status out of Garmin's FIT import response."""
    import_result = as_dict(as_dict(raw).get("detailedImportResult"))
    for upload in as_list(import_result.get("uploads")):
        if isinstance(upload, dict) and upload.get("status"):
            return str(upload["status"])
    return None


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
    value = _validate_weight(weight)
    timestamp = _resolve_timestamp(date)
    day = timestamp[:10]

    client = get_client()
    # add_body_composition() is absent from the oldest garminconnect releases this
    # package still allows, and would otherwise surface as an opaque AttributeError.
    if not callable(getattr(client, "add_body_composition", None)):
        return {
            "error": "This garminconnect version cannot write body composition. Upgrade to garminconnect>=0.3.0.",
            "written": False,
        }

    existing = _existing_on(client, day)

    try:
        raw = client.add_body_composition(
            timestamp=timestamp,
            weight=value,
            percent_fat=body_fat,
            percent_hydration=body_water,
            muscle_mass=muscle_mass,
            bone_mass=bone_mass,
            bmi=bmi,
            basal_met=basal_met,
            metabolic_age=metabolic_age,
        )
    except Exception as e:
        return {"error": str(e), "written": False}

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
