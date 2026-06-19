from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _error_client() -> MagicMock:
    m = MagicMock()
    m.get_activities_by_date.side_effect = Exception("API error")
    m.get_activity.side_effect = Exception("API error")
    m.get_sleep_data.side_effect = Exception("API error")
    m.get_hrv_data.side_effect = Exception("API error")
    m.get_stress_data.side_effect = Exception("API error")
    m.get_body_battery.side_effect = Exception("API error")
    m.get_spo2_data.side_effect = Exception("API error")
    m.get_respiration_data.side_effect = Exception("API error")
    m.get_intensity_minutes_data.side_effect = Exception("API error")
    m.get_user_summary.side_effect = Exception("API error")
    m.get_scheduled_workouts.side_effect = Exception("API error")
    m.get_training_status.side_effect = Exception("API error")
    m.get_training_readiness.side_effect = Exception("API error")
    m.get_training_plans.side_effect = Exception("API error")
    m.get_inprogress_virtual_challenges.side_effect = Exception("API error")
    m.get_badge_challenges.side_effect = Exception("API error")
    m.connectapi.side_effect = Exception("API error")
    return m


_ERROR_MODULES = [
    "garmin_mcp_lite.tools.activities",
    "garmin_mcp_lite.tools.health",
    "garmin_mcp_lite.tools.challenges",
    "garmin_mcp_lite.tools.coach",
    "garmin_mcp_lite.tools.events",
    "garmin_mcp_lite.tools.training",
    "garmin_mcp_lite.tools.weekly_stats",
]


@pytest.fixture()
def patch_error() -> None:
    c = _error_client()
    patchers = [patch(f"{mod}.get_client", return_value=c) for mod in _ERROR_MODULES]
    for p in patchers:
        p.start()
    yield
    for p in patchers:
        p.stop()


class TestActivitiesErrors:
    def test_list_activities_raises(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.activities import list_activities

        with pytest.raises(Exception, match="API error"):
            list_activities()

    def test_get_activity_detail_raises(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.activities import get_activity_detail

        with pytest.raises(Exception, match="API error"):
            get_activity_detail(123)


class TestHealthErrors:
    def test_sleep_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.health import get_health_data

        result = get_health_data(metric="sleep")
        assert "error" in result["sleep"]

    def test_hrv_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.health import get_health_data

        result = get_health_data(metric="hrv")
        assert "error" in result["hrv"]

    def test_stress_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.health import get_health_data

        result = get_health_data(metric="stress")
        assert "error" in result["stress"]

    def test_body_battery_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.health import get_health_data

        result = get_health_data(metric="body_battery")
        assert "error" in result["body_battery"]

    def test_spo2_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.health import get_health_data

        result = get_health_data(metric="spo2")
        assert "error" in result["spo2"]

    def test_respiration_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.health import get_health_data

        result = get_health_data(metric="respiration")
        assert "error" in result["respiration"]

    def test_intensity_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.health import get_health_data

        result = get_health_data(metric="intensity")
        assert "error" in result["intensity"]

    def test_steps_returns_empty(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.health import get_health_data

        result = get_health_data(metric="steps")
        # steps metric catches and silently ignores errors
        assert "daily_summary" not in result


class TestChallengesErrors:
    def test_returns_empty_on_exception(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.challenges import get_challenges

        result = get_challenges()
        assert result["virtual_challenges"] == []
        assert result["badge_challenges"] == []


class TestCoachErrors:
    def test_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.coach import get_coach_plans

        result = get_coach_plans()
        assert "error" in result


class TestEventsErrors:
    def test_returns_error_dict(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.events import get_events

        result = get_events()
        assert "error" in result


class TestTrainingErrors:
    def test_training_plan_handles_error(self, patch_error: None) -> None:
        from garmin_mcp_lite.tools.training import get_training_plan

        result = get_training_plan(date="2026-06-19")
        assert result["has_workout"] is False
