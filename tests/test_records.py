from __future__ import annotations

from unittest.mock import MagicMock

from garmin_mcp_lite.tools.records import get_personal_records


class TestPersonalRecords:
    def test_returns_all_mapped_records(self) -> None:
        result = get_personal_records()
        assert result["sport"] == "all"
        # typeId 28 (bench press) is not mapped and must be dropped
        assert result["count"] == 4
        types = [r["type"] for r in result["records"]]
        assert types == ["1k", "5k", "longest_run", "most_steps_day"]

    def test_formats_time_and_keeps_source_activity(self) -> None:
        result = get_personal_records(sport="running")
        by_type = {r["type"]: r for r in result["records"]}
        assert by_type["5k"]["value"] == "20:49"
        assert by_type["5k"]["date"] == "2025-10-13"
        assert by_type["5k"]["activity"] == "Tempo 14K"

    def test_formats_distance_and_counts(self) -> None:
        running = {r["type"]: r["value"] for r in get_personal_records(sport="running")["records"]}
        assert running["longest_run"] == "42.79 km"

        steps = get_personal_records(sport="steps")["records"]
        assert steps[0]["value"] == "46,963"

    def test_filters_by_sport(self) -> None:
        result = get_personal_records(sport="cycling")
        assert result["count"] == 0
        assert result["records"] == []


class TestPersonalRecordsErrors:
    def test_returns_error_dict(self, mock_get_client: MagicMock) -> None:
        mock_get_client.get_personal_record.side_effect = Exception("boom")
        assert get_personal_records()["error"] == "boom"
