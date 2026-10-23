"""Branch coverage for the defensive paths that the happy-path fixtures miss.

Every test here targets a specific `except` / `continue` / type-guard branch.
These are the branches that only fire on a malformed or partial Garmin response,
which is exactly when a silent crash would be most annoying — so they are worth
pinning even though they look trivial.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


def _client(**endpoints: object) -> MagicMock:
    """Build a fake client; pass an Exception to make that endpoint raise."""
    fake = MagicMock()
    for name, value in endpoints.items():
        if isinstance(value, BaseException):
            getattr(fake, name).side_effect = value
        else:
            getattr(fake, name).return_value = value
    return fake


def _use(module: str, fake: MagicMock):
    return patch(f"garmin_mcp_lite.tools.{module}.get_client", return_value=fake)


def _window(days_back: int = 10, days_fwd: int = 10) -> tuple[str, str]:
    today = datetime.now().date()
    return (
        (today - timedelta(days=days_back)).isoformat(),
        (today + timedelta(days=days_fwd)).isoformat(),
    )


# ── challenges ────────────────────────────────────────────────────────────────


class TestChallengesBranches:
    def test_distance_badge_is_converted_to_km(self) -> None:
        start, end = _window()
        fake = _client(
            get_inprogress_virtual_challenges=[],
            get_badge_challenges=[
                {
                    "badgeChallengeName": "Run 100K",
                    "startDate": f"{start}T00:00:00",
                    "endDate": f"{end}T00:00:00",
                    "badgeProgressValue": 25000,
                    "badgeTargetValue": 100000,
                    "badgeUnitId": 1,
                    "badgePoints": 100,
                    "userJoined": True,
                }
            ],
        )
        with _use("challenges", fake):
            from garmin_mcp_lite.tools.challenges import get_challenges

            result = get_challenges()

        badge = result["badge_challenges"][0]
        assert badge["unit"] == "km"
        assert badge["progress"] == 25.0
        assert badge["target"] == 100.0

    def test_badge_without_end_date_is_skipped(self) -> None:
        start, _ = _window()
        fake = _client(
            get_inprogress_virtual_challenges=[],
            get_badge_challenges=[
                {"badgeChallengeName": "No end", "startDate": f"{start}T00:00:00", "userJoined": True},
                {"badgeChallengeName": "No start", "endDate": "2030-01-01T00:00:00", "userJoined": True},
            ],
        )
        with _use("challenges", fake):
            from garmin_mcp_lite.tools.challenges import get_challenges

            result = get_challenges()

        assert result["badge_challenges"] == []

    def test_virtual_challenge_failure_is_swallowed(self) -> None:
        fake = _client(
            get_inprogress_virtual_challenges=RuntimeError("virtual down"),
            get_badge_challenges=[],
        )
        with _use("challenges", fake):
            from garmin_mcp_lite.tools.challenges import get_challenges

            result = get_challenges()

        assert result["virtual_challenges"] == []

    def test_badge_challenge_failure_is_swallowed(self) -> None:
        fake = _client(
            get_inprogress_virtual_challenges=[],
            get_badge_challenges=RuntimeError("badges down"),
        )
        with _use("challenges", fake):
            from garmin_mcp_lite.tools.challenges import get_challenges

            result = get_challenges()

        assert result["badge_challenges"] == []

    def test_virtual_challenge_with_zero_target_has_zero_percent(self) -> None:
        fake = _client(
            get_inprogress_virtual_challenges=[
                {"badgeChallengeName": "Zero", "badgeProgressValue": 5, "badgeTargetValue": 0, "badgePoints": 10}
            ],
            get_badge_challenges=[],
        )
        with _use("challenges", fake):
            from garmin_mcp_lite.tools.challenges import get_challenges

            result = get_challenges()

        assert result["virtual_challenges"][0]["percentage"] == 0


# ── coach ─────────────────────────────────────────────────────────────────────


class TestCoachBranches:
    def test_detail_lookup_failure_drops_the_plan(self) -> None:
        fake = _client(
            get_training_plans=["plan_x"],
            get_training_plan_by_id=RuntimeError("not found"),
        )
        with _use("coach", fake):
            from garmin_mcp_lite.tools.coach import get_coach_plans

            result = get_coach_plans()

        assert result == {"count": 0, "plans": []}

    def test_non_dict_detail_is_ignored(self) -> None:
        fake = _client(get_training_plans=["plan_x"], get_training_plan_by_id=["not", "a", "dict"])
        with _use("coach", fake):
            from garmin_mcp_lite.tools.coach import get_coach_plans

            result = get_coach_plans()

        assert result["count"] == 0


# ── gear ──────────────────────────────────────────────────────────────────────


class TestGearBranches:
    def test_stats_failure_falls_back_to_zero_distance(self) -> None:
        fake = _client(
            get_user_profile={"id": 1},
            get_gear=[{"uuid": "g1", "customMakeModel": "Shoes", "gearTypeName": "running_shoes"}],
            get_gear_stats=RuntimeError("no stats"),
        )
        with _use("gear", fake):
            from garmin_mcp_lite.tools.gear import get_gear_list

            result = get_gear_list()

        assert result["gear"][0]["distance_km"] == 0.0

    def test_gear_without_uuid_skips_the_stats_lookup(self) -> None:
        fake = _client(
            get_user_profile={"id": 1},
            get_gear=[{"gearMakeName": "Garmin", "gearTypeName": "bike"}],
        )
        with _use("gear", fake):
            from garmin_mcp_lite.tools.gear import get_gear_list

            result = get_gear_list()

        fake.get_gear_stats.assert_not_called()
        assert result["gear"][0]["name"] == "Garmin"
        assert result["gear"][0]["max_distance_km"] is None

    def test_gear_with_no_name_falls_back_to_unknown(self) -> None:
        fake = _client(get_user_profile={"id": 1}, get_gear=[{"uuid": "g1"}])
        with _use("gear", fake):
            from garmin_mcp_lite.tools.gear import get_gear_list

            result = get_gear_list()

        assert result["gear"][0]["name"] == "未知"


# ── health ────────────────────────────────────────────────────────────────────


class TestHealthBranches:
    def test_sleep_score_read_from_nested_sleep_scores(self) -> None:
        fake = _client(
            get_sleep_data={"dailySleepDTO": {"sleepScores": {"overall": {"value": 81}}}},
        )
        with _use("health", fake):
            from garmin_mcp_lite.tools.health import get_health_data

            result = get_health_data(metric="sleep")

        assert result["sleep"]["score"] == 81

    def test_sleep_durations_in_seconds_are_converted_to_minutes(self) -> None:
        # Garmin sometimes returns seconds; >1440 is the heuristic for "this is
        # not minutes", so 3600s must come back as 60 minutes.
        fake = _client(
            get_sleep_data={
                "dailySleepDTO": {
                    "sleepScore": 70,
                    "sleepTimeSeconds": 3600,
                    "deepSleepSeconds": 3000,
                    "remSleepSeconds": 1500,
                }
            },
        )
        with _use("health", fake):
            from garmin_mcp_lite.tools.health import get_health_data

            result = get_health_data(metric="sleep")

        assert result["sleep"]["duration_min"] == 60
        assert result["sleep"]["deep_min"] == 50
        assert result["sleep"]["rem_min"] == 25

    def test_body_battery_non_dict_payload_is_treated_as_empty(self) -> None:
        fake = _client(get_body_battery=[None])
        with _use("health", fake):
            from garmin_mcp_lite.tools.health import get_health_data

            result = get_health_data(metric="body_battery")

        assert result["body_battery"]["last_level"] is None

    def test_body_battery_last_level_from_array_tuples(self) -> None:
        fake = _client(
            get_body_battery=[{"bodyBatteryValuesArray": [[1000, 30], [2000, 42]]}],
        )
        with _use("health", fake):
            from garmin_mcp_lite.tools.health import get_health_data

            result = get_health_data(metric="body_battery")

        assert result["body_battery"]["last_level"] == 42

    def test_body_battery_last_level_from_array_dicts(self) -> None:
        fake = _client(
            get_body_battery=[{"bodyBatteryValuesArray": [{"bodyBatteryLevel": 55}]}],
        )
        with _use("health", fake):
            from garmin_mcp_lite.tools.health import get_health_data

            result = get_health_data(metric="body_battery")

        assert result["body_battery"]["last_level"] == 55

    def test_profile_failure_does_not_break_the_all_report(self) -> None:
        fake = _client(
            get_sleep_data={},
            get_hrv_data={},
            get_stress_data={},
            get_body_battery={},
            get_spo2_data={},
            get_respiration_data={},
            get_intensity_minutes_data={},
            get_user_profile=RuntimeError("profile down"),
            get_user_summary={},
        )
        with _use("health", fake):
            from garmin_mcp_lite.tools.health import get_health_data

            result = get_health_data(metric="all")

        assert "vo2max" not in result
        assert "daily_summary" in result


# ── hr_trend ──────────────────────────────────────────────────────────────────


class TestHrTrendBranches:
    def test_summary_failure_yields_no_data_instead_of_crashing(self) -> None:
        fake = _client(
            get_training_readiness=[],
            get_user_summary=RuntimeError("summary down"),
        )
        with _use("hr_trend", fake):
            from garmin_mcp_lite.tools.hr_trend import get_hr_trend

            result = get_hr_trend(period="7d")

        assert result["count"] == 0
        assert result["latest"] is None
        assert result["average"] is None
        assert result["min"] is None
        assert result["max"] is None


# ── race_prediction ───────────────────────────────────────────────────────────


class TestRacePredictionBranches:
    def test_missing_time_yields_nulls_not_a_crash(self) -> None:
        fake = _client(
            get_race_predictions={
                "calendarDate": "2026-06-18",
                "time5K": None,
                "time10K": 0,
                "timeHalfMarathon": 6249,
                "timeMarathon": 13819,
            }
        )
        with _use("race_prediction", fake):
            from garmin_mcp_lite.tools.race_prediction import get_race_prediction

            result = get_race_prediction()

        assert result["predictions"]["5k"] == {"time": None, "pace_per_km": None}
        assert result["predictions"]["10k"] == {"time": None, "pace_per_km": None}
        assert result["predictions"]["half_marathon"]["time"] == "1:44:09"

    def test_scalar_response_is_rejected(self) -> None:
        fake = _client(get_race_predictions="unexpected")
        with _use("race_prediction", fake):
            from garmin_mcp_lite.tools.race_prediction import get_race_prediction

            result = get_race_prediction()

        assert "error" in result

    def test_empty_list_response_is_rejected(self) -> None:
        fake = _client(get_race_predictions=[])
        with _use("race_prediction", fake):
            from garmin_mcp_lite.tools.race_prediction import get_race_prediction

            result = get_race_prediction()

        assert "error" in result

    def test_trend_window_failure_returns_error(self) -> None:
        fake = _client(get_race_predictions=RuntimeError("range down"))
        with _use("race_prediction", fake):
            from garmin_mcp_lite.tools.race_prediction import get_race_prediction

            result = get_race_prediction(period="90d")

        assert result == {"error": "range down"}

    def test_trend_window_with_no_rows_reports_the_window(self) -> None:
        fake = _client(get_race_predictions=[])
        with _use("race_prediction", fake):
            from garmin_mcp_lite.tools.race_prediction import get_race_prediction

            result = get_race_prediction(period="1y")

        assert "365 days" in result["error"]

    def test_trend_skips_distances_missing_from_either_end(self) -> None:
        fake = _client(
            get_race_predictions=[
                {"calendarDate": "2026-01-01", "time5K": 1300},
                {"calendarDate": "2026-06-01", "time5K": 1250, "time10K": 2700},
            ]
        )
        with _use("race_prediction", fake):
            from garmin_mcp_lite.tools.race_prediction import get_race_prediction

            result = get_race_prediction(period="90d")

        assert result["trend"]["change_s"]["5k"] == -50
        assert result["trend"]["change_s"]["10k"] is None
        assert result["trend"]["since"] == "2026-01-01"


# ── records ───────────────────────────────────────────────────────────────────


class TestRecordsBranches:
    def test_all_value_kinds_are_formatted(self) -> None:
        fake = _client(
            get_personal_record=[
                {"typeId": 9, "value": 1250.7},   # elevation_m
                {"typeId": 10, "value": 404.6},   # power_w
                {"typeId": 15, "value": 30.4},    # days
                {"typeId": 17, "value": 2000.0},  # distance_m
                {"typeId": 7, "value": 42791.8},  # distance_km
                {"typeId": 12, "value": 21500.0},  # count
            ]
        )
        with _use("records", fake):
            from garmin_mcp_lite.tools.records import get_personal_records

            result = get_personal_records()

        values = {r["type"]: r["value"] for r in result["records"]}
        assert values["max_elevation_gain"] == "1250 m"
        assert values["max_power"] == "404 W"
        assert values["longest_step_streak"] == "30 d"
        assert values["longest_pool_swim"] == "2000 m"
        assert values["longest_run"] == "42.79 km"
        assert values["most_steps_day"] == "21,500"

    def test_zero_and_non_numeric_values_are_dropped(self) -> None:
        fake = _client(
            get_personal_record=[
                {"typeId": 1, "value": 0},
                {"typeId": 2, "value": "not a number"},
                {"typeId": 3, "value": None},
            ]
        )
        with _use("records", fake):
            from garmin_mcp_lite.tools.records import get_personal_records

            result = get_personal_records()

        assert result["count"] == 0

    def test_sport_filter_keeps_only_that_discipline(self) -> None:
        fake = _client(
            get_personal_record=[
                {"typeId": 3, "value": 1249.0},
                {"typeId": 10, "value": 404.0},
            ]
        )
        with _use("records", fake):
            from garmin_mcp_lite.tools.records import get_personal_records

            result = get_personal_records(sport="cycling")

        assert [r["type"] for r in result["records"]] == ["max_power"]

    def test_short_or_missing_date_stamp_yields_null(self) -> None:
        fake = _client(get_personal_record=[{"typeId": 3, "value": 1249.0, "prStartTimeGmtFormatted": "2025"}])
        with _use("records", fake):
            from garmin_mcp_lite.tools.records import get_personal_records

            result = get_personal_records()

        assert result["records"][0]["date"] is None


# ── training ──────────────────────────────────────────────────────────────────


class TestTrainingPlanBranches:
    def test_default_date_is_today(self) -> None:
        fake = _client(get_scheduled_workouts={"calendarItems": []})
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_plan

            result = get_training_plan()

        assert result["date"] == datetime.now().strftime("%Y-%m-%d")
        assert result["has_workout"] is False

    def test_workout_lookup_failure_returns_a_message(self) -> None:
        fake = _client(get_scheduled_workouts=RuntimeError("calendar down"))
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_plan

            result = get_training_plan(date="2026-06-20")

        assert result["has_workout"] is False
        assert "calendar down" in result["message"]

    def test_items_are_filtered_by_date_and_type(self) -> None:
        fake = _client(
            get_scheduled_workouts={
                "calendarItems": [
                    "not a dict",
                    {"date": "2026-01-01", "itemType": "workout", "workoutId": 1},
                    {"date": "2026-06-20", "itemType": "note"},
                ]
            }
        )
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_plan

            result = get_training_plan(date="2026-06-20")

        assert result["has_workout"] is False

    def test_detail_fields_are_backfilled_from_the_calendar_item(self) -> None:
        fake = _client(
            get_scheduled_workouts={
                "calendarItems": [
                    {
                        "date": "2026-06-20",
                        "itemType": "workout",
                        "workoutId": 7,
                        "title": "Easy Spin",
                        "sportTypeKey": "cycling",
                    }
                ]
            },
            get_workout_by_id={"workoutId": 7},
        )
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_plan

            result = get_training_plan(date="2026-06-20")

        assert result["name"] == "Easy Spin"
        assert result["sport"] == "cycling"

    def test_non_dict_detail_falls_back_to_the_calendar_item(self) -> None:
        fake = _client(
            get_scheduled_workouts={
                "calendarItems": [
                    {"date": "2026-06-20", "itemType": "workout", "workoutId": 7, "title": "Spin"}
                ]
            },
            get_workout_by_id=["unexpected"],
        )
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_plan

            result = get_training_plan(date="2026-06-20")

        assert result["name"] == "Spin"

    def test_item_without_workout_id_is_used_directly(self) -> None:
        fake = _client(
            get_scheduled_workouts={
                "calendarItems": [
                    {
                        "date": "2026-06-20",
                        "itemType": "schedule",
                        "title": "Rest day",
                        "estimatedDurationInSecs": 1800,
                    }
                ]
            }
        )
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_plan

            result = get_training_plan(date="2026-06-20")

        fake.get_workout_by_id.assert_not_called()
        assert result["name"] == "Rest day"
        assert result["duration_min"] == 30


class TestTrainingStatusBranches:
    def test_degrades_gracefully_when_every_upstream_call_fails(self) -> None:
        fake = _client(
            get_activities_by_date=[
                {"activityName": "no date"},
                {"startTimeLocal": datetime.now().strftime("%Y-%m-%d")},
                {"startTimeLocal": "2026-01-01"},
                {"startTimeLocal": "2026-01-02"},
                {"startTimeLocal": "2026-01-03"},
                {"startTimeLocal": "2026-01-04"},
                {"startTimeLocal": "2026-01-05"},
                {"startTimeLocal": "2026-01-06"},
            ],
            get_max_metrics=RuntimeError("metrics down"),
            get_training_status=RuntimeError("status down"),
            get_training_readiness=RuntimeError("readiness down"),
        )
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_status

            result = get_training_status()

        assert result["vo2max"] is None
        assert result["training_status"] is None
        assert result["recovery_time_h"] is None
        assert result["readiness_score"] is None
        assert result["load_focus"] == {}
        # today + at most 4 activity dates
        assert len(result["source_dates"]["vo2max_candidates"]) == 5

    def test_vo2max_falls_through_to_the_next_candidate_date(self) -> None:
        fake = _client(
            get_activities_by_date=[{"startTimeLocal": "2026-01-01"}],
            get_training_status={},
            get_training_readiness=[],
        )
        fake.get_max_metrics.side_effect = [
            RuntimeError("no data today"),
            [{"generic": {"vo2MaxValue": 47}}],
        ]
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_status

            result = get_training_status()

        assert result["vo2max"] == 47
        assert fake.get_max_metrics.call_count == 2

    def test_activity_lookup_failure_still_yields_a_report(self) -> None:
        # The activity list only widens the VO2Max candidate dates; losing it
        # must not cost the user the rest of the training status.
        fake = _client(
            get_activities_by_date=RuntimeError("activities down"),
            get_max_metrics=[{"generic": {"vo2MaxValue": 46}}],
            get_training_status={},
            get_training_readiness=[],
        )
        with _use("training", fake):
            from garmin_mcp_lite.tools.training import get_training_status

            result = get_training_status()

        assert result["vo2max"] == 46
        assert result["source_dates"]["vo2max_candidates"] == [
            datetime.now().strftime("%Y-%m-%d")
        ]
