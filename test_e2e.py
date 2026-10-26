#!/usr/bin/env python3
"""端到端测试脚本 —— 逐个验证 garmin-mcp-lite 暴露的工具。

`garmin_sync_weight` 以 dry_run 模式执行：只读小米、只读 Garmin、不写入。
`garmin_add_body_composition` 是唯一的真实写入工具，不在这里自动执行：它会真的
往 Garmin 账号写数据。需要验证时单独用 `--write-test` 显式开启。

每个步骤独立 try/except：单个工具失败不会中断后续检查，
最后统一汇总。退出码非 0 表示至少有一个工具失败。

用法（需要先登录）:
    python test_e2e.py                 # 只跑读取 + 干跑同步
    python test_e2e.py --write-test    # 额外验证写入（会改动账号数据）
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


def check_body_composition() -> None:
    from garmin_mcp_lite.tools.body import get_body_composition

    result = get_body_composition(days=400, limit=3)
    if "error" in result:
        raise RuntimeError(result["error"])
    print(f"  记录数: {result['count']}（窗口 {result['range']['start']} ~ {result['range']['end']}）")
    for record in result["records"]:
        metrics = {k: v for k, v in record.items() if k not in ("date", "source")}
        print(f"    {record['date']}: {metrics} ({record.get('source')})")
    if result.get("change"):
        c = result["change"]
        print(f"  变化: {c['weight_kg']:+.2f} kg ({c['from']} -> {c['to']})")


def check_add_body_composition() -> None:
    """Write today's weight back to Garmin — only with --write-test."""
    from garmin_mcp_lite.tools.body import add_body_composition, get_body_composition

    current = get_body_composition(days=30, limit=1).get("latest") or {}
    weight = current.get("weight_kg")
    if not isinstance(weight, (int, float)):
        raise RuntimeError("账号里没有可复用的体重，跳过写入验证")

    print(f"  用最近一次的 {weight} kg 写回今天（会新增一条记录）")
    result = add_body_composition(weight=weight)
    if not result.get("written"):
        raise RuntimeError(result.get("error") or "写入失败")
    print(f"  written={result['written']} status={result.get('garmin_status')} date={result['date']}")
    if result.get("warning"):
        print(f"  ⚠️  {result['warning']}")



def check_sync_healthkit() -> None:
    """Dry-run the Apple Health bridge. Reads the bridge file and Garmin, writes nothing."""
    from garmin_mcp_lite.tools.healthkit import sync_healthkit

    result = sync_healthkit(dry_run=True)
    if result.get("error"):
        # No bridge file is a valid configuration (no iPhone shortcut set up yet).
        if "No Apple Health bridge file" in result["error"]:
            print("  未配置快捷指令桥接文件，跳过（不影响其他检查）")
            return
        raise RuntimeError(result["error"])
    bridge = result["bridge"]
    print(f"  桥接文件 {bridge['parsed']} 条 / {bridge['days']} 天（重复 {bridge['duplicate_timestamps']} 条）")
    for item in result["written"][:5]:
        print(f"    {item['date']}: {item['weight_kg']} kg")


def check_sync_weight() -> None:
    """Dry-run the Xiaomi -> Garmin sync. Reads both sides, writes nothing."""
    from garmin_mcp_lite.tools.weight_sync import sync_weight

    result = sync_weight(days=7, dry_run=True)
    if result.get("error"):
        # Not having a Xiaomi account is a valid configuration, not a failure.
        if "xiaomi-login" in result["error"]:
            print("  未配置小米账号，跳过（不影响其他检查）")
            return
        raise RuntimeError(result["error"])

    xiaomi = result["xiaomi"]
    print(f"  小米侧 {xiaomi['weigh_ins']} 次称重 / {xiaomi['days']} 天（同一天折叠 {xiaomi['same_day_collapsed']} 次）")
    print(f"  待写入 {len(result['written'])} 天 | Garmin 已有 {len(result['skipped'])} 天")
    for item in result["written"][:5]:
        print(f"    {item['date']}: {item['weight_kg']} kg")
    if result.get("note"):
        print(f"  注意: {result['note']}")


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


def check_status() -> None:
    from garmin_mcp_lite.tools.status import get_status

    result = get_status()
    garmin, xiaomi = result["garmin"], result["xiaomi"]
    print(f"  Garmin: {'ok (' + garmin['account'] + ')' if garmin['ok'] else garmin['detail']}")
    print(f"  Mi Fitness: {'ok' if xiaomi['ok'] else '未配置/已失效（仅 garmin_sync_weight 需要）'}")
    assert result["ready"], "Garmin token 不可用，请先运行 garmin-mcp-lite-login"


_STEPS = [
    ("garmin_status", check_status),
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
    ("garmin_body_composition", check_body_composition),
    ("garmin_sync_weight (dry run)", check_sync_weight),
    ("garmin_sync_healthkit (dry run)", check_sync_healthkit),
]


def main() -> int:
    print("=" * 50)
    print("garmin-mcp-lite 端到端测试")
    print("=" * 50)

    steps = list(_STEPS)
    if "--write-test" in sys.argv[1:]:
        # Opt-in only: this appends a weigh-in to the real account.
        steps.append(("garmin_add_body_composition", check_add_body_composition))
        print("⚠️  已启用写入验证，会往账号新增一条今天的体重记录")

    failures: list[str] = []
    total = len(steps)

    for index, (name, step) in enumerate(steps, start=1):
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
