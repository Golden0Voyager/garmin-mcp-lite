from importlib.metadata import PackageNotFoundError, version

from mcp.server.fastmcp import FastMCP

from garmin_mcp_lite.tools import (
    activities,
    body,
    challenges,
    coach,
    device,
    events,
    gear,
    health,
    hr_trend,
    race_prediction,
    records,
    status,
    training,
    weekly_stats,
    weight_sync,
    zones,
)


def _package_version() -> str:
    try:
        return version("garmin-mcp-lite")
    except PackageNotFoundError:  # running from a source tree with no install
        return "0.0.0+unknown"


mcp = FastMCP("garmin-mcp-lite")

# FastMCP takes no `version` argument, so the low-level server falls back to the
# version of the `mcp` package itself — clients then show serverInfo.version as
# e.g. "1.30.0", which is misleading in bug reports. InitializationOptions are
# built lazily inside run(), so assigning the attribute here is sufficient.
mcp._mcp_server.version = _package_version()

mcp.add_tool(status.get_status, name="garmin_status")
mcp.add_tool(activities.list_activities, name="garmin_activities")
mcp.add_tool(activities.get_activity_detail, name="garmin_activity_detail")
mcp.add_tool(training.get_training_plan, name="garmin_training_plan")
mcp.add_tool(training.get_training_status, name="garmin_training_status")
mcp.add_tool(health.get_health_data, name="garmin_health")
mcp.add_tool(gear.get_gear_list, name="garmin_gear")
mcp.add_tool(device.get_device_info, name="garmin_device")
mcp.add_tool(hr_trend.get_hr_trend, name="garmin_hr_trend")
mcp.add_tool(weekly_stats.get_weekly_stats, name="garmin_weekly_stats")
mcp.add_tool(coach.get_coach_plans, name="garmin_coach")
mcp.add_tool(events.get_events, name="garmin_events")
mcp.add_tool(challenges.get_challenges, name="garmin_challenges")
mcp.add_tool(race_prediction.get_race_prediction, name="garmin_race_prediction")
mcp.add_tool(records.get_personal_records, name="garmin_personal_records")
mcp.add_tool(zones.get_zones, name="garmin_zones")
mcp.add_tool(body.get_body_composition, name="garmin_body_composition")
mcp.add_tool(body.add_body_composition, name="garmin_add_body_composition")
mcp.add_tool(weight_sync.sync_weight, name="garmin_sync_weight")


def main():
    mcp.run()


if __name__ == "__main__":
    main()  # pragma: no cover - only reached when run as a script
