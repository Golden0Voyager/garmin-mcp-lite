from __future__ import annotations

import re
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp_lite.tools import body as body_mod
from garmin_mcp_lite.tools._common import today_str
from garmin_mcp_lite.tools.body import add_body_composition, get_body_composition

_ISO_SECONDS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class TestMassNormalisation:
    def test_grams_become_kilograms(self, mock_get_client: MagicMock) -> None:
        record = get_body_composition()["records"][0]

        assert record["weight_kg"] == 69.8
        assert record["muscle_mass_kg"] == 32.1
        assert record["bone_mass_kg"] == 3.1

    def test_values_already_in_kilograms_are_left_alone(self, mock_get_client: MagicMock) -> None:
        # A third-party scale can push kilograms upstream; 70.2 must not become 0.07.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"calendarDate": "2026-01-01", "weight": 70.2, "muscleMass": 32.1}],
        }

        record = get_body_composition()["records"][0]

        assert record["weight_kg"] == 70.2
        assert record["muscle_mass_kg"] == 32.1

    def test_zero_and_negative_mass_are_treated_as_missing(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"calendarDate": "2026-01-01", "weight": 0, "muscleMass": -5}],
        }

        record = get_body_composition()["records"][0]

        assert record == {"date": "2026-01-01"}

    def test_booleans_are_not_numbers(self, mock_get_client: MagicMock) -> None:
        # isinstance(True, int) is True in Python; a naive check would emit 1 kg.
        assert body_mod._to_kg(True) is None
        assert body_mod._to_kg(None) is None
        assert body_mod._to_kg("69.8") is None


class TestGetBodyComposition:
    def test_records_are_newest_first(self, mock_get_client: MagicMock) -> None:
        dates = [r["date"] for r in get_body_composition()["records"]]

        assert dates == ["2025-09-26", "2025-09-20"]

    def test_null_fields_are_dropped(self, mock_get_client: MagicMock) -> None:
        # An MFP-synced row only has weight. Emitting eight nulls wastes tokens and
        # makes the model report "body fat: null" as if it were a measurement.
        oldest = get_body_composition()["records"][1]

        assert oldest == {"date": "2025-09-20", "weight_kg": 70.2, "source": "MFP"}

    def test_full_metrics_are_returned(self, mock_get_client: MagicMock) -> None:
        latest = get_body_composition()["latest"]

        assert latest["bmi"] == 22.1
        assert latest["body_fat_pct"] == 18.4
        assert latest["body_water_pct"] == 55.2
        assert latest["visceral_fat"] == 8
        assert latest["metabolic_age"] == 36
        assert latest["source"] == "INDEX_SCALE"

    def test_change_is_newest_minus_oldest(self, mock_get_client: MagicMock) -> None:
        change = get_body_composition()["change"]

        assert change == {"weight_kg": -0.4, "from": "2025-09-20", "to": "2025-09-26"}

    def test_average_comes_from_total_average(self, mock_get_client: MagicMock) -> None:
        assert get_body_composition()["average"] == {"weight_kg": 70.0}

    def test_average_carries_body_fat_when_garmin_computes_it(self, mock_get_client: MagicMock) -> None:
        # totalAverage has the same shape as a row, so a populated account gets
        # averages for the composition metrics too.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"calendarDate": "2026-01-01", "weight": 70000.0}],
            "totalAverage": {"weight": 70000.0, "bmi": 22.14, "bodyFat": 18.44, "bodyWater": 55.25},
        }

        average = get_body_composition()["average"]

        assert average == {"weight_kg": 70.0, "bmi": 22.14, "body_fat_pct": 18.44, "body_water_pct": 55.25}

    def test_count_reports_every_row_not_the_limited_page(self, mock_get_client: MagicMock) -> None:
        result = get_body_composition(limit=1)

        assert result["count"] == 2
        assert len(result["records"]) == 1

    def test_empty_history(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {"dateWeightList": []}

        result = get_body_composition()

        assert result["count"] == 0
        assert result["records"] == []
        assert result["latest"] is None
        assert "change" not in result

    def test_null_payload_does_not_raise(self, mock_get_client: MagicMock) -> None:
        # Garmin answers an empty window with explicit nulls, not an empty list.
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = None

        assert get_body_composition()["records"] == []

    def test_api_failure_returns_error(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = RuntimeError("boom")

        assert get_body_composition()["error"] == "boom"

    def test_days_are_clamped(self, mock_get_client: MagicMock) -> None:
        get_body_composition(days=99999)

        start, end = mock_get_client.get_body_composition.call_args[0]
        expected = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
        assert start == expected
        assert end == today_str()


class TestAddBodyComposition:
    def test_writes_the_measurement(self, mock_get_client: MagicMock) -> None:
        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["written"] is True
        assert result["weight_kg"] == 70.5
        assert result["date"] == "2026-10-23"

    def test_forwards_every_metric_under_the_library_keyword_names(
        self, mock_get_client: MagicMock
    ) -> None:
        add_body_composition(
            weight=70.5,
            date="2026-10-23",
            body_fat=18.4,
            body_water=55.2,
            muscle_mass=32.1,
            bone_mass=3.1,
            bmi=22.1,
            basal_met=1650,
            metabolic_age=36,
        )

        kwargs = mock_get_client.add_body_composition.call_args.kwargs
        # The public API uses percent_fat / percent_hydration, not body_fat /
        # body_water; a silent rename here would drop the metric on the floor.
        assert kwargs["weight"] == 70.5
        assert kwargs["percent_fat"] == 18.4
        assert kwargs["percent_hydration"] == 55.2
        assert kwargs["muscle_mass"] == 32.1
        assert kwargs["bone_mass"] == 3.1
        assert kwargs["bmi"] == 22.1
        assert kwargs["basal_met"] == 1650
        assert kwargs["metabolic_age"] == 36

    def test_bare_date_is_recorded_in_the_morning(self, mock_get_client: MagicMock) -> None:
        add_body_composition(weight=70.5, date="2026-10-23")

        assert mock_get_client.add_body_composition.call_args.kwargs["timestamp"] == "2026-10-23T07:00:00"

    def test_full_timestamp_is_preserved(self, mock_get_client: MagicMock) -> None:
        add_body_composition(weight=70.5, date="2026-10-23T21:15:30")

        assert mock_get_client.add_body_composition.call_args.kwargs["timestamp"] == "2026-10-23T21:15:30"

    def test_missing_date_defaults_to_now(self, mock_get_client: MagicMock) -> None:
        add_body_composition(weight=70.5)

        timestamp = mock_get_client.add_body_composition.call_args.kwargs["timestamp"]
        assert _ISO_SECONDS.match(timestamp)

    def test_invalid_date_is_rejected(self, mock_get_client: MagicMock) -> None:
        with pytest.raises(ValueError, match="ISO 8601"):
            add_body_composition(weight=70.5, date="23/10/2026")

    def test_grams_are_rejected_with_a_pointer_to_the_cause(self, mock_get_client: MagicMock) -> None:
        # The read path hands back grams, so a read-modify-write is the natural
        # way to get here. The message has to name the mistake.
        with pytest.raises(ValueError, match="looks like grams"):
            add_body_composition(weight=69800)

        mock_get_client.add_body_composition.assert_not_called()

    def test_non_positive_weight_is_rejected(self, mock_get_client: MagicMock) -> None:
        for bad in (0, -1):
            with pytest.raises(ValueError, match="positive"):
                add_body_composition(weight=bad)

    def test_non_numeric_weight_is_rejected(self, mock_get_client: MagicMock) -> None:
        with pytest.raises(ValueError, match="must be a number"):
            add_body_composition(weight="70.5")  # type: ignore[arg-type]

    def test_boolean_weight_is_rejected(self, mock_get_client: MagicMock) -> None:
        with pytest.raises(ValueError, match="must be a number"):
            add_body_composition(weight=True)

    def test_only_supplied_metrics_are_echoed(self, mock_get_client: MagicMock) -> None:
        result = add_body_composition(weight=70.5, body_fat=18.4)

        assert result["body_fat_pct"] == 18.4
        assert "bmi" not in result
        assert "muscle_mass_kg" not in result

    def test_upload_status_is_reported(self, mock_get_client: MagicMock) -> None:
        assert add_body_composition(weight=70.5)["garmin_status"] == "SUCCESS"

    def test_missing_status_is_tolerated(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.return_value = None

        result = add_body_composition(weight=70.5)

        assert result["written"] is True
        assert "garmin_status" not in result

    def test_absent_status_falls_back_to_reading_the_day_back(self, mock_get_client: MagicMock) -> None:
        # Live testing showed the upload response can carry no status at all, so
        # the tool has to confirm the entry by reading it back.
        mock_get_client.add_body_composition.return_value = {}
        mock_get_client.get_body_composition.side_effect = [
            {"dateWeightList": []},  # pre-write duplicate check
            {"dateWeightList": [{"calendarDate": "2026-10-23", "weight": 70500.0, "sourceType": "INDEX_SCALE"}]},
        ]

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["verified"] is True
        assert result["stored"] == {"weight_kg": 70.5, "source": "INDEX_SCALE"}

    def test_readback_that_disagrees_is_not_verified(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.return_value = {}
        mock_get_client.get_body_composition.side_effect = [
            {"dateWeightList": []},
            {"dateWeightList": [{"calendarDate": "2026-10-23", "weight": 75000.0}]},
        ]

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["verified"] is False

    def test_readback_that_finds_nothing_is_not_verified(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.return_value = {}
        mock_get_client.get_body_composition.side_effect = [
            {"dateWeightList": []},
            {"dateWeightList": []},
        ]

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["verified"] is False
        assert "stored" not in result

    def test_duplicate_day_produces_a_warning(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = None
        mock_get_client.get_body_composition.return_value = {
            "dateWeightList": [{"calendarDate": "2026-10-23", "weight": 70200.0, "sourceType": "MFP"}],
        }

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert "already had 70.2 kg" in result["warning"]
        assert "MFP" in result["warning"]
        # The write still happens: Garmin is the one that decides about duplicates.
        assert result["written"] is True

    def test_fresh_day_has_no_warning(self, mock_get_client: MagicMock) -> None:
        assert "warning" not in add_body_composition(weight=70.5, date="2026-10-23")

    def test_lookup_failure_does_not_block_the_write(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_body_composition.side_effect = RuntimeError("lookup down")

        result = add_body_composition(weight=70.5, date="2026-10-23")

        assert result["written"] is True

    def test_api_failure_returns_error(self, mock_get_client: MagicMock) -> None:
        mock_get_client.add_body_composition.side_effect = RuntimeError("upload rejected")

        result = add_body_composition(weight=70.5)

        assert result["written"] is False
        assert result["error"] == "upload rejected"

    def test_old_garminconnect_gets_a_readable_error(self) -> None:
        # add_body_composition() is missing from the oldest versions this package
        # still allows; an AttributeError would tell the user nothing.
        legacy = MagicMock(spec=["get_body_composition"])

        with patch.object(body_mod, "get_client", return_value=legacy):
            result = add_body_composition(weight=70.5)

        assert result["written"] is False
        assert "garminconnect>=0.3.0" in result["error"]
