from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

_TOOL_MODULES = [
    # onboarding is not a tool module, but its probes call get_client(); the
    # autouse patch keeps the garmin_status tool off the real token store.
    "garmin_mcp_lite.onboarding",
    "garmin_mcp_lite.tools.activities",
    "garmin_mcp_lite.tools.body",
    "garmin_mcp_lite.tools.challenges",
    "garmin_mcp_lite.tools.coach",
    "garmin_mcp_lite.tools.cycling",
    "garmin_mcp_lite.tools.device",
    "garmin_mcp_lite.tools.dive",
    "garmin_mcp_lite.tools.events",
    "garmin_mcp_lite.tools.gear",
    "garmin_mcp_lite.tools.health",
    "garmin_mcp_lite.tools.healthkit",
    "garmin_mcp_lite.tools.hr_trend",
    "garmin_mcp_lite.tools.hrv",
    "garmin_mcp_lite.tools.ledger",
    "garmin_mcp_lite.tools.race_prediction",
    "garmin_mcp_lite.tools.records",
    "garmin_mcp_lite.tools.strength",
    "garmin_mcp_lite.tools.training",
    "garmin_mcp_lite.tools.weekly_stats",
    "garmin_mcp_lite.tools.weight_sync",
    "garmin_mcp_lite.tools.workouts",
    "garmin_mcp_lite.tools.zones",
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
        "metadataDTO": {"hasHrTimeInZones": True, "hasPowerTimeInZones": True},
        "summaryDTO": {
            "startTimeLocal": "2026-06-18 07:30:00",
            "distance": 5230.0, "duration": 1860.0, "calories": 420.0,
            "averageHR": 148.0, "maxHR": 172.0, "elevationGain": 35.0,
            "averageSpeed": 2.81, "vO2MaxValue": 48,
            "averageRunningCadenceInStepsPerMinute": 82, "steps": 5230,
            "activityTrainingLoad": 77.4,
            "trainingEffect": 3.0,
            "trainingEffectLabel": "AEROBIC_BASE",
            "anaerobicTrainingEffect": 0.0,
            "aerobicTrainingEffectMessage": "IMPROVING_AEROBIC_BASE_8",
            "anaerobicTrainingEffectMessage": "NO_ANAEROBIC_BENEFIT_0",
        },
    }
    fake.get_activity_laps.return_value = {"lapDTOs": [{"lapIndex": 1, "distance": 1000.0}]}
    fake.get_activity_weather.return_value = {
        "temp": 26.0,
        "apparentTemp": 28.0,
        "relativeHumidity": 61.0,
        "windSpeed": 12.0,
        "windDirectionCompassPoint": "SE",
        "weatherTypeDTO": {"desc": "Partly Cloudy"},
    }
    fake.get_activity_gear_v2.return_value = [
        None,
        {
            "uuid": "gear_001",
            "gearType": "SHOES",
            "name": "Strong Wind 3.0 TR",
            "brand": "Qiandan",
            "model": "Strong Wind 3.0 TR",
            "maxUsageDistanceMeters": 643000.0,
            "numActivitiesLinked": 51,
            "distanceUsedMeters": 461664.5,
        }
    ]
    fake.get_activity_typed_splits.return_value = {
        "activityId": 12345,
        "splits": [
            {
                "type": "INTERVAL_ACTIVE",
                "distance": 5230.0,
                "duration": 1860.0,
                "averageSpeed": 2.81,
                "averageHR": 148.0,
            }
        ],
    }

    # -- health --
    fake.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "sleepTimeSeconds": 25200,
            "deepSleepSeconds": 5400,
            "lightSleepSeconds": 12000,
            "remSleepSeconds": 6300,
            "awakeSleepSeconds": 1260,
            "awakeCount": 3,
            "sleepStartTimestampLocal": "2026-06-17T23:00:00.0",
            "sleepEndTimestampLocal": "2026-06-18T06:00:00.0",
            "averageSpO2Value": 96.0,
            "lowestSpO2Value": 92.0,
            "averageRespirationValue": 14.5,
            "lowestRespirationValue": 11.8,
            "highestRespirationValue": 17.2,
            "avgSleepStress": 18,
            "sleepScores": {
            "overall": {"value": 78, "qualifierKey": "FAIR"},
            "deepPercentage": {"value": 22, "qualifierKey": "EXCELLENT"},
            "totalDuration": {"qualifierKey": "GOOD"},
        },
        },
        "restlessMomentsCount": 6,
        "avgOvernightHrv": 52.0,
        "hrvStatus": "BALANCED",
        "bodyBatteryChange": 40,
        "restingHeartRate": 45,
    }
    fake.get_lifestyle_logging_data.return_value = {
        "calendarDate": "2026-11-27",
        "dailyLogsReport": [
            {"name": "Alcohol", "category": "LIFESTYLE", "measurementType": "QUANTITY", "sleepRelated": False},
            {"name": "Morning Caffeine", "category": "LIFESTYLE", "measurementType": "QUANTITY", "sleepRelated": False},
            {"name": "Screens Before Bed", "category": "SLEEP_RELATED", "measurementType": "NONE", "sleepRelated": True},
        ],
        "completionStats": [
            {"calendarDate": "2026-11-26", "totalTracking": 15, "completedTracking": 2},
            {"calendarDate": "2026-11-27", "totalTracking": 15, "completedTracking": 1},
        ],
    }
    fake.get_hrv_data.return_value = {
        "hrvSummary": {
            "calendarDate": "2026-11-08",
            "weeklyAvg": 52.3,
            "lastNightAvg": 48.0,
            "lastNight5MinHigh": 64,
            "baseline": {"lowUpper": 47, "balancedLow": 50, "balancedUpper": 66},
            "status": "BALANCED",
            "feedbackPhrase": "HRV_BALANCED",
        },
        "hrvReadings": [{"hrvValue": 48, "readingTimeGmt": "2026-11-08T00:00:00.0"}],
    }
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
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "workoutSteps": [
                    {"stepOrder": 1, "targetType": {"workoutTargetTypeKey": "pace"}, "targetValueOne": 5.5, "targetValueTwo": 6.5, "targetValueUnit": "min/km"},
                ],
            }
        ],
    }
    fake.get_max_metrics.return_value = [{"generic": {"vo2MaxValue": 48, "vo2MaxPreciseValue": 48.2}}]
    fake.get_training_status.return_value = {
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                "dev1": {
                    "primaryTrainingDevice": True,
                    "trainingStatus": 6,
                    "trainingStatusFeedbackPhrase": "Productive training load",
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": 280,
                        "dailyTrainingLoadChronic": 636,
                        "dailyAcuteChronicWorkloadRatio": 0.9,
                        "acwrPercent": 38,
                        "acwrStatus": "OPTIMAL",
                        "minTrainingLoadChronic": 508.8,
                        "maxTrainingLoadChronic": 954.0,
                    },
                },
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
    fake.get_rhr_daily.return_value = [
        None,
        {"calendarDate": "2026-06-17", "value": 50.0},
        {"calendarDate": "2026-06-18", "value": 48.0},
    ]
    # Live endpoint returns newest-first, same as get_training_readiness_range.
    fake.get_training_readiness_range.return_value = [
        {
            "score": 85,
            "level": "HIGH",
            "recoveryTime": 720,
            "sleepScore": 82,
            "restingHeartRate": 48,
            "calendarDate": "2026-06-18",
            "timestampLocal": "2026-06-18T08:00:00",
            "feedbackShort": "GOOD_TO_GO",
            "feedbackLong": "READY_FOR_CHALLENGE",
            "hrvWeeklyAverage": 52,
            "sleepScoreFactorPercent": 88,
            "sleepScoreFactorFeedback": "GOOD",
            "recoveryTimeFactorPercent": 90,
            "recoveryTimeFactorFeedback": "GOOD",
            "acwrFactorPercent": 93,
            "acwrFactorFeedback": "GOOD",
            "stressHistoryFactorPercent": 97,
            "stressHistoryFactorFeedback": "GOOD",
            "hrvFactorPercent": 53,
            "hrvFactorFeedback": "MODERATE",
            "sleepHistoryFactorPercent": 65,
            "sleepHistoryFactorFeedback": "MODERATE",
        },
        {
            "score": 70,
            "level": "MODERATE",
            "recoveryTime": 1080,
            "sleepScore": 74,
            "restingHeartRate": 50,
            "calendarDate": "2026-06-17",
            "timestampLocal": "2026-06-17T08:00:00",
        },
    ]
    fake.get_training_four_week_load_balance.return_value = {
        "userId": 123456,
        "metricsTrainingLoadBalanceDTOMap": {
            "dev1": {
                "calendarDate": "2026-06-18",
                "deviceId": 1,
                "monthlyLoadAerobicLow": 1251.9,
                "monthlyLoadAerobicHigh": 1112.1,
                "monthlyLoadAnaerobic": 120.2,
                "monthlyLoadAerobicLowTargetMin": 433,
                "monthlyLoadAerobicLowTargetMax": 952,
                "monthlyLoadAerobicHighTargetMin": 519,
                "monthlyLoadAerobicHighTargetMax": 1039,
                "monthlyLoadAnaerobicTargetMin": 173,
                "monthlyLoadAnaerobicTargetMax": 519,
                "trainingBalanceFeedbackPhrase": "ANAEROBIC_SHORTAGE",
                "primaryTrainingDevice": True,
            }
        },
    }
    fake.get_fitnessage_data.return_value = {
        "chronologicalAge": 38,
        "fitnessAge": 30.105706878811105,
        "achievableFitnessAge": 32.587329130811334,
        "previousFitnessAge": 30.105706878811105,
        "components": {
            "bodyFat": {"value": 16.5, "stale": False, "lastMeasurementDate": "2026-06-18"},
            "rhr": {"value": 43, "stale": False},
            "vigorousDaysAvg": {"value": 5.0, "stale": False, "numOfWeeksForIm": 6},
            "vigorousMinutesAvg": {"value": 291.3, "stale": False, "numOfWeeksForIm": 6},
        },
        "lastUpdated": "2026-06-18T00:00:00.0",
    }

    # -- challenges --
    fake.get_inprogress_virtual_challenges.return_value = [{"badgeChallengeName": "Climb 5000m", "badgeProgressValue": 3200, "badgeTargetValue": 5000, "badgePoints": 100}]
    fake.get_badge_challenges.return_value = [{"badgeChallengeName": "June Challenge", "startDate": "2026-06-01T00:00:00", "endDate": "2026-06-30T00:00:00", "badgeProgressValue": 45, "badgeTargetValue": 100, "badgeUnitId": 1, "badgePoints": 50, "userJoined": True}]

    # -- coach --
    fake.get_training_plans.return_value = {
        "trainingPlanList": [{"trainingPlanId": "plan_001", "trainingPlanName": "Half Marathon Plan", "sportType": {"sportTypeKey": "running"}, "trainingPlanStatus": "ACTIVE", "startDate": "2026-06-01", "endDate": "2026-08-15", "trainingPlanGoal": "Complete half marathon"}],
        "searchFilter": {},
    }

    # -- device --
    fake.get_devices.return_value = [{"deviceId": 123, "displayName": "My Fenix 7", "partNumber": "F7X-045-01", "currentFirmwareVersion": "28.10", "softwareUpdates": [], "deviceStatus": "ACTIVE", "primaryActivityTrackerIndicator": True, "primaryTrainingCapable": True, "registeredDate": 1700000000000, "connected": True}]

    # -- events --
    def _day(offset: int) -> str:
        return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")

    def _fake_connectapi(path: str) -> list:
        if path == "/calendar-service/events":
            return [
                {
                    # Already ran: the tool must drop it, not report it as upcoming.
                    "eventName": "Spring 10K", "date": _day(-30), "eventType": "running",
                    "completionTarget": None, "eventCustomization": None,
                },
                {
                    # Returned out of order on purpose: the tool sorts soonest first.
                    "eventName": "Tokyo Marathon", "date": _day(130), "eventType": "running",
                    "completionTarget": {"value": 42.195},
                    "eventCustomization": {"isPrimaryEvent": True, "customGoal": {"unitType": "time", "value": 14400}, "trainingPlanId": "plan_marathon"},
                },
                {
                    # Real shape for an event with no custom goal: both nested
                    # objects are explicit nulls, not absent keys.
                    "eventName": "Local 10K", "date": _day(8), "eventType": "running",
                    "completionTarget": None,
                    "eventCustomization": {"isPrimaryEvent": False, "customGoal": None, "trainingPlanId": None},
                },
            ]
        if path == "/biometric-service/heartRateZones":
            return [
                {"trainingMethod": "HR_RESERVE", "restingHeartRateUsed": 43, "lactateThresholdHeartRateUsed": 166, "zone1Floor": 130, "zone2Floor": 141, "zone3Floor": 155, "zone4Floor": 172, "zone5Floor": 183, "maxHeartRateUsed": 198, "sport": "RUNNING"},
                {"trainingMethod": "HR_MAX", "restingHeartRateUsed": 43, "lactateThresholdHeartRateUsed": 160, "zone1Floor": 94, "zone2Floor": 113, "zone3Floor": 132, "zone4Floor": 150, "zone5Floor": 169, "maxHeartRateUsed": 188, "sport": "CYCLING"},
            ]
        if path == "/activity-service/activity/88001":
            return {
                "activityId": 88001,
                "activityName": "Road Cycling",
                "startTimeLocal": "2026-11-06 14:50:34",
                "activityType": {"typeKey": "cycling"},
                "summaryDTO": {
                    "duration": 3600.0,
                    "distance": 30000.0,
                    "averageSpeed": 8.33,
                    "maxSpeed": 12.5,
                    "avgPower": 165.0,
                    "maxPower": 320.0,
                    "normalizedPower": 178.0,
                    "trainingStressScore": 68.5,
                    "intensityFactor": 0.92,
                    "averageBikeCadence": 85.0,
                    "maxBikeCadence": 105.0,
                    "elevationGain": 150.0,
                    "averageHR": 142.0,
                    "maxHR": 165.0,
                    "calories": 620.0,
                },
            }
        if path == "/activity-service/activity/88002":
            return {
                "activityId": 88002,
                "activityName": "Strength Session",
                "activityType": {"typeKey": "strength_training"},
                "summaryDTO": {
                    "startTimeLocal": "2026-11-08T17:53:11.0",
                    "duration": 2400.0,
                    "averageHR": 85.0,
                    "maxHR": 120.0,
                    "calories": 180.0,
                    "activityTrainingLoad": 5.0,
                },
            }
        if path == "/activity-service/activity/88002/exerciseSets":
            return {
                "activityId": 88002,
                "exerciseSets": [
                    {
                        "setType": "ACTIVE",
                        "duration": 60.0,
                        "repetitionCount": 10,
                        "weight": 60000.0,
                        "exercises": [{"category": "SQUAT", "name": "Back Squat"}],
                    },
                    {
                        "setType": "REST",
                        "duration": 90.0,
                    },
                    {
                        "setType": "ACTIVE",
                        "duration": 45.0,
                        "repetitionCount": 12,
                        "weight": 20000.0,
                        "exercises": [{"category": "BENCH_PRESS", "name": "Dumbbell Press"}],
                    },
                ],
            }
        if path == "/activity-service/activity/99001":
            return {
                "activityId": 99001,
                "activityName": "Karangasem Freediving",
                "startTimeLocal": "2026-08-18 14:47:19",
                "activityType": {"typeKey": "apnea_diving"},
                "summaryDTO": {
                    "maxDepth": 25.4,
                    "averageDepth": 12.3,
                    "diveCount": 18,
                    "bottomTime": 1420.0,
                    "maxBottomTime": 115.0,
                    "surfaceInterval": 3200.0,
                    "averageTemperature": 28.5,
                    "minHR": 48.0,
                    "averageHR": 78.0,
                    "maxHR": 95.0,
                    "activityTrainingLoad": 12.5,
                },
            }
        return []

    fake.connectapi.side_effect = _fake_connectapi

    # -- gear --
    fake.get_gear.return_value = [{"uuid": "gear_001", "customMakeModel": "Nike Vaporfly 3", "gearTypeName": "running_shoes", "maximumMeters": 800000, "retired": False, "defaultGear": True}]
    fake.get_gear_stats.return_value = {"totalDistance": 450000}
    fake.get_fastest_splits.return_value = [
        {"distance": 1000, "activityId": 24193607983, "activityDate": "2026-09-01", "time": 195.772},
        {"distance": 1000, "activityId": 22032716924, "activityDate": "2026-03-02", "time": 203.314},
        {"distance": 5000, "activityId": 24193607983, "activityDate": "2026-09-01", "time": 991.505},
    ]

    # -- race prediction --
    def _fake_race_predictions(startdate: str | None = None, enddate: str | None = None, _type: str | None = None) -> object:
        latest = {
            "calendarDate": "2026-06-18", "time5K": 1295, "time10K": 2763,
            "timeHalfMarathon": 6249, "timeMarathon": 13819,
        }
        if startdate:
            return [
                {
                    "calendarDate": "2026-04-30", "time5K": 1329, "time10K": 2849,
                    "timeHalfMarathon": 6433, "timeMarathon": 14208,
                },
                latest,
            ]
        return latest

    fake.get_race_predictions.side_effect = _fake_race_predictions

    # -- personal records --
    fake.get_personal_record.return_value = [
        {"typeId": 1, "value": 219.94200134277344, "prStartTimeGmtFormatted": "2025-02-13T05:16:42.0", "activityName": "Treadmill"},
        {"typeId": 3, "value": 1249.27294921875, "prStartTimeGmtFormatted": "2025-10-13T09:35:18.0", "activityName": "Tempo 14K"},
        {"typeId": 7, "value": 42791.80859375, "prStartTimeGmtFormatted": "2025-11-02T01:00:00.0", "activityName": "Long Run"},
        {"typeId": 12, "value": 46963.0, "prStartTimeLocalFormatted": "2025-12-14T00:00:00.0", "activityName": None},
        {"typeId": 28, "value": 100.0, "prStartTimeGmtFormatted": "2025-01-01T00:00:00.0", "activityName": "Gym"},
    ]

    # -- zones / thresholds --
    # The zone payload is served by connectapi() above, because
    # Garmin.get_heart_rate_zones() does not exist on every supported
    # garminconnect version (it is missing in 0.3.3).
    fake.get_lactate_threshold.return_value = {
        "speed_and_heart_rate": {"speed": None, "heartRate": 166},
        "power": {"functionalThresholdPower": 404, "isStale": True},
    }
    fake.get_cycling_ftp.return_value = {"functionalThresholdPower": 194, "calendarDate": "2025-07-30T13:30:42.373", "isStale": True}

    # -- body composition --
    # Real shape: mass is in grams (69800.0 == 69.8 kg) and a scale that only
    # syncs weight (sourceType MFP) leaves every other metric as an explicit null.
    _body_rows = [
        {
            "calendarDate": "2025-09-20", "weight": 70200.0, "bmi": None, "bodyFat": None,
            "bodyWater": None, "boneMass": None, "muscleMass": None, "physiqueRating": None,
            "visceralFat": None, "metabolicAge": None, "sourceType": "MFP",
        },
        {
            "calendarDate": "2025-09-26", "weight": 69800.0, "bmi": 22.1, "bodyFat": 18.4,
            "bodyWater": 55.2, "boneMass": 3100.0, "muscleMass": 32100.0, "physiqueRating": 3,
            "visceralFat": 8, "metabolicAge": 36, "sourceType": "INDEX_SCALE",
        },
    ]

    def _fake_body_composition(startdate: str, enddate: str | None = None) -> dict:
        # The write path asks for a single day to check for an existing entry;
        # return nothing there so tests opt in to the duplicate case explicitly.
        rows = [] if enddate == startdate else _body_rows
        return {
            "startDate": startdate,
            "endDate": enddate,
            "dateWeightList": rows,
            "totalAverage": {
                "from": 1758153600000, "until": 1792799999999, "weight": 70000.0,
                "bmi": None, "bodyFat": None, "bodyWater": None, "boneMass": None,
                "muscleMass": None, "physiqueRating": None, "visceralFat": None, "metabolicAge": None,
            },
        }

    fake.get_body_composition.side_effect = _fake_body_composition
    fake.add_body_composition.return_value = {
        "detailedImportResult": {
            "uploadId": 987654,
            "uploads": [{"status": "SUCCESS", "fileType": "FIT"}],
            "successes": [],
            "failures": [],
        }
    }

    return fake
