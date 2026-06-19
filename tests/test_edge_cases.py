from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def edge_client() -> MagicMock:
    """Mock client with edge-case return values for uncovered branches."""
    fake = MagicMock()

    # For challenges with time-based unit (unit_id=7)
    fake.get_inprogress_virtual_challenges.return_value = []
    fake.get_badge_challenges.return_value = [
        {
            "badgeChallengeName": "Time Challenge",
            "startDate": "2026-06-01T00:00:00",
            "endDate": "2026-06-30T00:00:00",
            "badgeProgressValue": 3600,
            "badgeTargetValue": 7200,
            "badgeUnitId": 7,
            "badgePoints": 50,
            "userJoined": True,
        }
    ]

    # For coach with string plan IDs
    fake.get_training_plans.return_value = ["plan_str_id"]
    fake.get_training_plan_by_id.return_value = {
        "trainingPlanId": "plan_str_id",
        "trainingPlanName": "String ID Plan",
        "sportType": {"sportTypeKey": "cycling"},
        "trainingPlanStatus": "ACTIVE",
        "startDate": "2026-07-01",
        "endDate": "2026-09-01",
        "trainingPlanGoal": "Century ride",
    }

    # For hr_trend fallback: readiness fails → summary succeeds
    fake.get_training_readiness.side_effect = Exception("no readiness")
    fake.get_user_summary.return_value = {"restingHeartRate": 55}

    # For training: calendarItems as list (not dict with "calendarItems" key)
    fake.get_scheduled_workouts.return_value = [
        {
            "date": "2026-06-20",
            "itemType": "workout",
            "workoutId": 888,
            "title": "Interval Session",
            "sportTypeKey": "running",
            "estimatedDurationInSecs": 3600,
        }
    ]
    # get_workout_by_id fails → fallback to item
    fake.get_workout_by_id.side_effect = Exception("detail not found")
    fake.get_max_metrics.side_effect = Exception("no metrics")
    fake.get_training_status.return_value = {
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                "dev1": {
                    "primaryTrainingDevice": True,
                    "trainingStatus": 6,
                    "trainingStatusFeedbackPhrase": "Productive",
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": 280,
                        "acwrStatus": "OPTIMAL",
                    },
                }
            }
        },
        "mostRecentTrainingLoadBalance": {
            "trainingLoad": 280,
            "metricsTrainingLoadBalanceDTOMap": {
                "dev1": {
                    "primaryTrainingDevice": True,
                    "monthlyLoadAnaerobic": 120,
                    "monthlyLoadAerobicHigh": 300,
                    "monthlyLoadAerobicLow": 450,
                    "trainingBalanceFeedbackPhrase": "Balanced",
                }
            },
        },
    }
    fake.get_training_readiness.return_value = []
    fake.get_activities_by_date.return_value = []

    # For activities optional fields: each raises
    fake.get_activity.return_value = {
        "activityName": "Test", "activityTypeDTO": {"typeKey": "running"},
        "metadataDTO": {"startTimeLocal": "2026-06-18T07:00:00"},
        "summaryDTO": {"distance": 5000, "duration": 1800, "calories": 300, "averageHR": 140, "maxHR": 165, "averageSpeed": 2.78},
    }
    fake.get_activity_splits.side_effect = Exception("no splits")
    fake.get_activity_hr_in_timezones.side_effect = Exception("no hr zones")
    fake.get_activity_laps.side_effect = Exception("no laps")

    return fake


_EDGE_MODULES = [
    "garmin_mcp_lite.tools.challenges",
    "garmin_mcp_lite.tools.coach",
    "garmin_mcp_lite.tools.hr_trend",
    "garmin_mcp_lite.tools.training",
    "garmin_mcp_lite.tools.activities",
]


@pytest.fixture()
def patch_edge(edge_client: MagicMock) -> None:
    patchers = [patch(f"{mod}.get_client", return_value=edge_client) for mod in _EDGE_MODULES]
    for p in patchers:
        p.start()
    yield
    for p in patchers:
        p.stop()


class TestChallengesTimeUnit:
    def test_time_unit_conversion(self, patch_edge: None) -> None:
        from garmin_mcp_lite.tools.challenges import get_challenges

        result = get_challenges()
        assert len(result["badge_challenges"]) == 1
        bc = result["badge_challenges"][0]
        assert bc["unit"] == "hours"
        assert bc["progress"] == 1.0  # 3600s → 1 hour
        assert bc["target"] == 2.0  # 7200s → 2 hours


class TestCoachStringId:
    def test_str_plan_id(self, patch_edge: None) -> None:
        from garmin_mcp_lite.tools.coach import get_coach_plans

        result = get_coach_plans()
        assert result["count"] == 1
        assert result["plans"][0]["name"] == "String ID Plan"


class TestHrTrendFallback:
    def test_readiness_fails_falls_back_to_summary(self, patch_edge: None) -> None:
        from garmin_mcp_lite.tools.hr_trend import get_hr_trend

        result = get_hr_trend(period="7d")
        assert result["count"] >= 1
        assert result["latest"]["value"] == 55


class TestTrainingListCalendarItems:
    def test_calendar_items_as_list(self, patch_edge: None) -> None:
        from garmin_mcp_lite.tools.training import get_training_plan

        result = get_training_plan(date="2026-06-20")
        assert result["has_workout"] is True


class TestActivitiesOptionalFieldsErrors:
    def test_splits_error_returns_error_dict(self, patch_edge: None) -> None:
        from garmin_mcp_lite.tools.activities import get_activity_detail

        result = get_activity_detail(999, fields=["splits", "hrZones", "laps"])
        assert "error" in result["splits"]
        assert "error" in result["hr_zones"]
        assert "error" in result["laps"]
