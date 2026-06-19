from mcp.server.fastmcp import FastMCP

from garmin_mcp_lite.tools import (
    activities,
    challenges,
    coach,
    device,
    events,
    gear,
    health,
    hr_trend,
    training,
    weekly_stats,
)

mcp = FastMCP("garmin-mcp-lite")

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

def main():
    mcp.run()

if __name__ == "__main__":
    main()
