from datetime import datetime, timedelta
from typing import Literal

from garmin_mcp_lite.client import get_client


def get_hr_trend(
    period: Literal["7d", "30d", "90d"] = "7d",
) -> dict:
    """获取静息心率历史趋势数据。

    Args:
        period: 时间范围
    """
    client = get_client()

    period_days = {"7d": 7, "30d": 30, "90d": 90}
    days = period_days.get(period, 7)
    end = datetime.now()
    start = end - timedelta(days=days)

    raw_rows: list[dict] = []
    for i in range(days):
        check_date = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            readiness_list = client.get_training_readiness(check_date)
            if isinstance(readiness_list, list) and readiness_list:
                rhr = readiness_list[0].get("restingHeartRate")
                if rhr:
                    raw_rows.append({"date": check_date, "value": int(rhr)})
        except Exception:
            pass

    # 按日期聚合并排序，保证 latest 的语义稳定
    by_date: dict[str, list[int]] = {}
    for row in raw_rows:
        by_date.setdefault(row["date"], []).append(row["value"])

    hr_data = [
        {"date": date, "value": round(sum(values) / len(values), 1)}
        for date, values in by_date.items()
    ]
    hr_data.sort(key=lambda x: x["date"], reverse=True)

    # 计算统计
    values = [d["value"] for d in hr_data if d["value"]]
    return {
        "period": period,
        "metric": "resting",
        "date_range": f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}",
        "count": len(hr_data),
        "latest": hr_data[0] if hr_data else None,
        "average": round(sum(values) / len(values), 1) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "data": hr_data[:10],  # 最近10条
    }
