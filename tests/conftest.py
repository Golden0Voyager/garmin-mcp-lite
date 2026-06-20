from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

_TOOL_MODULES = [
    "garmin_mcp_lite.tools.activities",
    "garmin_mcp_lite.tools.health",
    "garmin_mcp_lite.tools.challenges",
    "garmin_mcp_lite.tools.coach",
    "garmin_mcp_lite.tools.device",
    "garmin_mcp_lite.tools.events",
    "garmin_mcp_lite.tools.gear",
    "garmin_mcp_lite.tools.hr_trend",
    "garmin_mcp_lite.tools.training",
    "garmin_mcp_lite.tools.weekly_stats",
]


@pytest.fixture(autouse=True)
def mock_get_client() -> Generator[MagicMock]:
    fake = _build_fake()

    patchers = [patch(f"{mod}.get_client", return_value=fake) for mod in _TOOL_MODULES]
    for p in patchers:
        p.start()
    yield fake
    for p in patchers:
        p.stop()


def _build_fake() -> MagicMock:
    fake = MagicMock()

    # -- activities --
    fake.get_activities_by_date.return_value = [
        {
            "activityId": 12345, "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "startTimeLocal": "2026-06-18 07:30:00",
            "distance": 5230.0, "duration": 1860.0, "calories": 420,
            "averageHR": 148, "maxHR": 172, "averageSpeed": 2.81, "vO2MaxValue": 48,
        },
        {
            "activityId": 12346, "activityName": "Evening Ride",
            "activityType": {"typeKey": "cycling"},
            "startTimeLocal": "2026-06-17 18:00:00",
            "distance": 25100.0, "duration": 3720.0, "calories": 680,
            "averageHR": 135, "maxHR": 162, "averageSpeed": 6.75,
        },
    ]
    fake.get_activity.return_value = {
        "activityName": "Morning Run",
        "activityTypeDTO": {"typeKey": "running"},
        "metadataDTO": {"startTimeLocal": "2026-06-18 07:30:00"},
        "summaryDTO": {
            "distance": 5230.0, "duration": 1860.0, "calories": 420.0,
            "averageHR": 148.0, "maxHR": 172.0, "elevationGain": 35.0,
            "averageSpeed": 2.81, "vO2MaxValue": 48,
            "averageRunningCadenceInStepsPerMinute": 82, "steps": 5230,
        },
    }

    # -- health --
    fake.get_sleep_data.return_value = {
        "dailySleepDTO": {"sleepTimeInMinutes": 420, "deepSleepMinutes": 90, "remSleepMinutes": 105, "awakeCount": 3, "sleepScore": 78},
    }
    fake.get_hrv_data.return_value = {"hrvSummary": {"weeklyAvg": 52.3, "lastNightAvg": 48.0, "status": "BALANCED"}}
    fake.get_stress_data.return_value = {"avgStressLevel": 35, "maxStressLevel": 72, "restStressLevel": 18}
    fake.get_spo2_data.return_value = {"averageSpO2": 97.0, "lowestSpO2": 94.0, "latestSpO2": 98.0, "lastSevenDaysAvgSpO2": 96.5}
    fake.get_respiration_data.return_value = {"avgWakingRespirationValue": 14.2, "lowestRespirationValue": 11.0, "highestRespirationValue": 18.5}
    fake.get_body_battery.return_value = [{"bodyBatteryMostRecentValue": 65, "bodyBatteryChargedValue": 42, "bodyBatteryDrainedValue": 38}]
    fake.get_intensity_minutes_data.return_value = {"weeklyTotal": 320, "weekGoal": 150, "weeklyVigorous": 120, "weeklyModerate": 200}
    fake.get_user_summary.return_value = {"totalSteps": 8542, "dailyStepGoal": 10000, "floorsAscended": 12, "userFloorsAscendedGoal": 10, "restingHeartRate": 52}
    fake.get_user_profile.return_value = {"userData": {"vo2MaxRunning": 48}, "id": 123456}

    # -- training --
    fake.get_scheduled_workouts.return_value = {
        "calendarItems": [
            {"date": "2026-06-19", "itemType": "workout", "workoutId": 999, "title": "Easy Recovery Run", "sportTypeKey": "running", "estimatedDurationInSecs": 2700, "workoutSteps": [{"stepOrder": 1, "targetType": {"workoutTargetTypeKey": "pace", "targetValueOne": 5.5, "targetValueTwo": 6.5, "targetValueUnit": "min/km"}}]},
        ],
    }
    fake.get_workout_by_id.return_value = {
        "workoutId": 999, "workoutName": "Easy Recovery Run",
        "sportType": {"sportTypeKey": "running"}, "estimatedDurationInSecs": 2700,
        "description": "Easy recovery run at conversational pace.",
        "workoutSteps": [{"stepOrder": 1, "targetType": {"workoutTargetTypeKey": "pace", "targetValueOne": 5.5, "targetValueTwo": 6.5, "targetValueUnit": "min/km"}}],
    }
    fake.get_max_metrics.return_value = [{"generic": {"vo2MaxValue": 48, "vo2MaxPreciseValue": 48.2}}]
    fake.get_training_status.return_value = {
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                "dev1": {"primaryTrainingDevice": True, "trainingStatus": 6, "trainingStatusFeedbackPhrase": "Productive training load", "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 280, "acwrStatus": "OPTIMAL"}},
            },
        },
        "mostRecentTrainingLoadBalance": {
            "trainingLoad": 280,
            "metricsTrainingLoadBalanceDTOMap": {
                "dev1": {"primaryTrainingDevice": True, "monthlyLoadAnaerobic": 120, "monthlyLoadAerobicHigh": 300, "monthlyLoadAerobicLow": 450, "trainingBalanceFeedbackPhrase": "Balanced"},
            },
        },
    }
    fake.get_training_readiness.return_value = [{"score": 85, "recoveryTime": 720, "sleepScore": 82, "restingHeartRate": 48, "calendarDate": "2026-06-18", "timestampLocal": "2026-06-18T08:00:00"}]

    # -- challenges --
    fake.get_inprogress_virtual_challenges.return_value = [{"badgeChallengeName": "Climb 5000m", "badgeProgressValue": 3200, "badgeTargetValue": 5000, "badgePoints": 100}]
    fake.get_badge_challenges.return_value = [{"badgeChallengeName": "June Challenge", "startDate": "2026-06-01T00:00:00", "endDate": "2026-06-30T00:00:00", "badgeProgressValue": 45, "badgeTargetValue": 100, "badgeUnitId": 1, "badgePoints": 50, "userJoined": True}]

    # -- coach --
    fake.get_training_plans.return_value = [{"trainingPlanId": "plan_001", "trainingPlanName": "Half Marathon Plan", "sportType": {"sportTypeKey": "running"}, "trainingPlanStatus": "ACTIVE", "startDate": "2026-06-01", "endDate": "2026-08-15", "trainingPlanGoal": "Complete half marathon"}]

    # -- device --
    fake.get_devices.return_value = [{"deviceId": 123, "displayName": "My Fenix 7", "partNumber": "F7X-045-01", "currentFirmwareVersion": "28.10", "softwareUpdates": [], "deviceStatus": "ACTIVE", "primaryActivityTrackerIndicator": True, "primaryTrainingCapable": True, "registeredDate": 1700000000000, "connected": True}]

    # -- events --
    def _fake_connectapi(path: str) -> list:
        if path == "/calendar-service/events":
            return [{"eventName": "Tokyo Marathon", "date": "2027-03-07", "eventType": "running", "completionTarget": {"value": 42.195}, "eventCustomization": {"isPrimaryEvent": True, "customGoal": {"unitType": "time", "value": 14400}, "trainingPlanId": "plan_marathon"}}]
        return []

    fake.connectapi.side_effect = _fake_connectapi

    # -- gear --
    fake.get_gear.return_value = [{"uuid": "gear_001", "customMakeModel": "Nike Vaporfly 3", "gearTypeName": "running_shoes", "maximumMeters": 800000, "retired": False, "defaultGear": True}]
    fake.get_gear_stats.return_value = {"totalDistance": 450000}

    return fake
