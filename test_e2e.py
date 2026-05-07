#!/usr/bin/env python3
"""端到端测试脚本 - 逐个验证 garmin-mcp-lite 工具"""
import sys


def test_login():
    print("\n[1/10] 测试登录...")
    from garmin_mcp_lite.client import get_client
    client = get_client()
    name = client.get_full_name()
    print(f"  ✅ 登录成功: {name}")


def test_activities():
    print("\n[2/10] 测试 garmin_activities...")
    from garmin_mcp_lite.tools.activities import list_activities
    result = list_activities(limit=3)
    print(f"  获取到 {result['count']} 条活动")
    for act in result["activities"]:
        print(f"    - {act['date']} | {act['type']} | {act['distance_km']}km | {act['pace']}")
    print("  ✅ 通过")


def test_activity_detail():
    print("\n[3/10] 测试 garmin_activity_detail...")
    from garmin_mcp_lite.tools.activities import get_activity_detail, list_activities
    acts = list_activities(limit=1)
    if acts["count"] == 0:
        print("  ⚠️ 无活动可测，跳过")
        return
    act_id = acts["activities"][0]["id"]
    detail = get_activity_detail(act_id)
    print(f"  活动: {detail['name']} | {detail['distance_km']}km | {detail['duration_min']}min")
    print("  ✅ 通过")


def test_training_plan():
    print("\n[4/10] 测试 garmin_training_plan...")
    from garmin_mcp_lite.tools.training import get_training_plan
    result = get_training_plan()
    if result["has_workout"]:
        print(f"  今日课表: {result['name']} | {result['sport']} | {result['duration_min']}min")
    else:
        print("  今日无课表")
    print("  ✅ 通过")


def test_training_status():
    print("\n[5/10] 测试 garmin_training_status...")
    from garmin_mcp_lite.tools.training import get_training_status
    result = get_training_status()
    print(
        f"  VO2Max: {result.get('vo2max')} | 准备度: {result.get('readiness_score')}"
        f" | 恢复时间: {result.get('recovery_time_h')}h"
    )
    print("  ✅ 通过")


def test_health():
    print("\n[6/10] 测试 garmin_health...")
    from garmin_mcp_lite.tools.health import get_health_data
    result = get_health_data(metric="sleep")
    sleep = result.get("sleep", {})
    if "error" not in sleep:
        print(f"  睡眠: {sleep.get('duration_min')}min | 深度睡眠: {sleep.get('deep_min')}min")
    else:
        print(f"  睡眠数据: {sleep.get('error')}")
    print("  ✅ 通过")


def test_gear():
    print("\n[7/10] 测试 garmin_gear...")
    from garmin_mcp_lite.tools.gear import get_gear_list
    result = get_gear_list()
    print(f"  装备数: {result['count']}")
    for g in result["gear"][:3]:
        print(f"    - {g['name']} | {g['type']} | {g['distance_km']}km")
    print("  ✅ 通过")


def test_hr_trend():
    print("\n[8/10] 测试 garmin_hr_trend...")
    from garmin_mcp_lite.tools.hr_trend import get_hr_trend
    result = get_hr_trend(period="7d")
    print(f"  最近7天静息心率: {result.get('average')} bpm (基于 {result.get('count')} 条记录)")
    print("  ✅ 通过")


def test_weekly_stats():
    print("\n[9/10] 测试 garmin_weekly_stats...")
    from garmin_mcp_lite.tools.weekly_stats import get_weekly_stats
    result = get_weekly_stats(period="week")
    print(
        f"  本周: {result.get('total_activities')} 次活动 | "
        f"{result.get('total_distance_km')} km | {result.get('total_duration_hours')} h"
    )
    print("  ✅ 通过")


def test_coach():
    print("\n[10/10] 测试 garmin_coach...")
    from garmin_mcp_lite.tools.coach import get_coach_plans
    result = get_coach_plans()
    print(f"  Coach 计划数: {result.get('count')}")
    print("  ✅ 通过")


def main():
    print("=" * 50)
    print("garmin-mcp-lite 端到端测试")
    print("=" * 50)

    try:
        test_login()
        test_activities()
        test_activity_detail()
        test_training_plan()
        test_training_status()
        test_health()
        test_gear()
        test_hr_trend()
        test_weekly_stats()
        test_coach()
        print("\n" + "=" * 50)
        print("🎉 全部测试通过")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
