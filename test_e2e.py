#!/usr/bin/env python3
"""端到端测试脚本 —— 逐个验证 garmin-mcp-lite 暴露的全部 15 个工具。

每个步骤独立 try/except：单个工具失败不会中断后续检查，
最后统一汇总。退出码非 0 表示至少有一个工具失败。

用法（需要先登录）:
    python test_e2e.py
"""
from __future__ import annotations

import sys
import traceback


def check_login() -> None:
    from garmin_mcp_lite.client import get_client

    name = get_client().get_full_name()
    print(f"  登录成功: {name}")


def check_activities() -> None:
    from garmin_mcp_lite.tools.activities import list_activities

    result = list_activities(limit=3)
    print(f"  获取到 {result['count']} 条活动")
    for act in result["activities"]:
        print(f"    - {act['date']} | {act['type']} | {act['distance_km']}km | {act['pace']}")


def check_activity_detail() -> None:
    from garmin_mcp_lite.tools.activities import get_activity_detail, list_activities

    acts = list_activities(limit=1)
    if acts["count"] == 0:
        print("  无活动可测，跳过")
        return
    act_id = acts["activities"][0]["id"]
    detail = get_activity_detail(act_id)
    print(f"  活动: {detail['name']} | {detail['distance_km']}km | {detail['duration_min']}min")


def check_training_plan() -> None:
    from garmin_mcp_lite.tools.training import get_training_plan

    result = get_training_plan()
    if result["has_workout"]:
        print(f"  今日课表: {result['name']} | {result['sport']} | {result['duration_min']}min")
    else:
        print("  今日无课表")


def check_training_status() -> None:
    from garmin_mcp_lite.tools.training import get_training_status

    result = get_training_status()
    print(
        f"  VO2Max: {result.get('vo2max')} | 准备度: {result.get('readiness_score')}"
        f" | 恢复时间: {result.get('recovery_time_h')}h"
    )


def check_health() -> None:
    from garmin_mcp_lite.tools.health import get_health_data

    sleep = get_health_data(metric="sleep").get("sleep", {})
    if "error" not in sleep:
        print(f"  睡眠: {sleep.get('duration_min')}min | 深度睡眠: {sleep.get('deep_min')}min")
    else:
        print(f"  睡眠数据: {sleep.get('error')}")


def check_gear() -> None:
    from garmin_mcp_lite.tools.gear import get_gear_list

    result = get_gear_list()
    print(f"  装备数: {result['count']}")
    for g in result["gear"][:3]:
        print(f"    - {g['name']} | {g['type']} | {g['distance_km']}km")


def check_device() -> None:
    from garmin_mcp_lite.tools.device import get_device_info

    result = get_device_info()
    print(f"  设备数: {result['count']}")
    for d in result["devices"][:3]:
        print(f"    - {d['name']} | fw {d['firmware_version']} | 更新: {d['has_update']}")


def check_hr_trend() -> None:
    from garmin_mcp_lite.tools.hr_trend import get_hr_trend

    result = get_hr_trend(period="7d")
    print(f"  最近7天静息心率: {result.get('average')} bpm (基于 {result.get('count')} 条记录)")


def check_weekly_stats() -> None:
    from garmin_mcp_lite.tools.weekly_stats import get_weekly_stats

    result = get_weekly_stats(period="week")
    print(
        f"  本周: {result.get('total_activities')} 次活动 | "
        f"{result.get('total_distance_km')} km | {result.get('total_duration_hours')} h"
    )


def check_coach() -> None:
    from garmin_mcp_lite.tools.coach import get_coach_plans

    print(f"  Coach 计划数: {get_coach_plans().get('count')}")


def check_events() -> None:
    from garmin_mcp_lite.tools.events import get_events

    result = get_events()
    if "error" in result:
        raise RuntimeError(result["error"])
    print(f"  赛事数: {result['count']}")
    for e in result["events"][:3]:
        print(f"    - {e['name']} | {e['date']} | {e['distance_km']}km | 目标: {e['goal_time']}")


def check_challenges() -> None:
    from garmin_mcp_lite.tools.challenges import get_challenges

    result = get_challenges()
    print(
        f"  虚拟挑战: {len(result['virtual_challenges'])} 个 | "
        f"进行中徽章: {len(result['badge_challenges'])} 个"
    )


def check_race_prediction() -> None:
    from garmin_mcp_lite.tools.race_prediction import get_race_prediction

    result = get_race_prediction()
    if "error" in result:
        raise RuntimeError(result["error"])
    preds = result["predictions"]
    print(f"  预测日期: {result['date']}")
    for label in ("5k", "10k", "half_marathon", "marathon"):
        print(f"    - {label}: {preds[label]['time']} ({preds[label]['pace_per_km']}/km)")


def check_personal_records() -> None:
    from garmin_mcp_lite.tools.records import get_personal_records

    result = get_personal_records(sport="running")
    print(f"  跑步个人纪录: {result['count']} 项")
    for r in result["records"][:5]:
        print(f"    - {r['type']}: {r['value']} ({r['date']})")


def check_zones() -> None:
    from garmin_mcp_lite.tools.zones import get_zones

    result = get_zones(sport="running")
    if "error" in result:
        raise RuntimeError(result["error"])
    hr = result["hr_zones"]
    print(f"  分区方法: {hr.get('method')} | MaxHR: {hr.get('max_hr')} | LTHR: {hr.get('lthr')}")
    for z in hr.get("zones", []):
        print(f"    Z{z['zone']} {z['label']}: {z['min']}-{z['max']} bpm")
    lt = result.get("lactate_threshold", {})
    if "error" not in lt:
        print(f"  乳酸阈值: {lt.get('heart_rate')} bpm | {lt.get('pace_per_km')}/km")


_STEPS = [
    ("登录", check_login),
    ("garmin_activities", check_activities),
    ("garmin_activity_detail", check_activity_detail),
    ("garmin_training_plan", check_training_plan),
    ("garmin_training_status", check_training_status),
    ("garmin_health", check_health),
    ("garmin_gear", check_gear),
    ("garmin_device", check_device),
    ("garmin_hr_trend", check_hr_trend),
    ("garmin_weekly_stats", check_weekly_stats),
    ("garmin_coach", check_coach),
    ("garmin_events", check_events),
    ("garmin_challenges", check_challenges),
    ("garmin_race_prediction", check_race_prediction),
    ("garmin_personal_records", check_personal_records),
    ("garmin_zones", check_zones),
]


def main() -> int:
    print("=" * 50)
    print("garmin-mcp-lite 端到端测试")
    print("=" * 50)

    failures: list[str] = []
    total = len(_STEPS)

    for index, (name, step) in enumerate(_STEPS, start=1):
        print(f"\n[{index}/{total}] 测试 {name} ...")
        try:
            step()
            print("  ✅ 通过")
        except Exception as e:  # noqa: BLE001 - report and keep going
            print(f"  ❌ 失败: {e}")
            traceback.print_exc()
            failures.append(name)

    print("\n" + "=" * 50)
    if failures:
        print(f"❌ {len(failures)}/{total} 个步骤失败: {', '.join(failures)}")
        print("=" * 50)
        return 1

    print(f"🎉 全部 {total} 个步骤通过")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
