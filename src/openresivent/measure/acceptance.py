"""现场验收辅助，规则转述：JGJ/T 440-2018 7.3.4–7.3.7，GB 55015-2021 6.3.13。"""

import itertools
import math
from datetime import datetime


def flow_deviation(design: float, measured: float, *, terminal: bool = False) -> dict:
    """设计和实测风量 m³/s → 偏差比例及是否在允许范围内。"""
    if design <= 0 or measured < 0:
        raise ValueError("设计风量须为正、实测风量不可为负")
    deviation = measured / design - 1
    limit = 0.15 if terminal else 0.10
    return {
        "deviation": deviation,
        "limit": limit,
        "passed": abs(deviation) <= limit + 1e-12,
        "source": "GB 55015-2021 6.3.13 转述",
    }


def required_homes(total: int) -> int:
    """建筑总户数 → 不小于 5% 且至少一户的抽检户数。"""
    if total < 1:
        raise ValueError("总户数须为正")
    return max(1, math.ceil(total * 0.05))


def continuous_monitor(records: list[dict], *, pm25_removal: bool = True) -> dict:
    """输入按时间排列的室外、室内 PM2.5（kg/m³）和室内 CO₂ 体积分数。

    每条包含 time（ISO 日期时间）、outdoor_pm、indoor_pm、indoor_co2；输出所选日期、
    浓度均值和测量条件，规则来自 JGJ/T 440-2018 7.3.5。最严重日按日均室外浓度排序。
    """
    if len(records) < 2:
        raise ValueError("监测数据不足")
    times = [datetime.fromisoformat(r["time"]) for r in records]
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(times)]
    if any(g <= 0 for g in gaps):
        raise ValueError("时间戳须严格递增")
    if (
        max(gaps) > 600
        or len(set(gaps)) != 1
        or 86400 % gaps[0] != 0
        or (times[-1] - times[0]).total_seconds() + gaps[0] < 30 * 86400
    ):
        raise ValueError("监测需至少30天、等间隔且不超过10分钟，间隔须整除一天")
    if any(min(r["outdoor_pm"], r["indoor_pm"], r["indoor_co2"]) < 0 for r in records):
        raise ValueError("浓度不能为负")
    days = {}
    for date, row in zip(times, records, strict=True):
        days.setdefault(date.date(), []).append((date, row))
    daily = {
        str(day): sum(r["outdoor_pm"] for _, r in rows) / len(rows)
        for day, rows in days.items()
        if len(rows) == 86400 / gaps[0]
        and rows[0][0].hour == 0
        and rows[0][0].minute == 0
        and rows[0][0].second == 0
    }
    if len(daily) < 30:
        raise ValueError("完整采样日不足 30 天")
    if pm25_removal and sum(x > 75e-9 for x in daily.values()) < 5:
        raise ValueError("室外 PM2.5 日均超过 75 μg/m³ 的天数不足 5 天")
    chosen = sorted(daily, key=lambda d: (-daily[d], d))[:5]
    sample = [r for t, r in zip(times, records) if str(t.date()) in chosen]
    return {
        "selected_days": chosen,
        "indoor_pm": sum(r["indoor_pm"] for r in sample) / len(sample),
        "indoor_co2": sum(r["indoor_co2"] for r in sample) / len(sample),
        "source": "JGJ/T 440-2018 7.3.5 转述",
    }


def track_judgement(
    pm25: float,
    co2: float,
    *,
    design_pm: float = 50e-9,
    design_co2: float = 0.001,
    acceptance_pm: float = 75e-9,
    acceptance_co2: float = 0.001,
) -> dict:
    """室内 PM2.5 kg/m³、CO₂ 体积分数及限值 → 设计轨和验收轨分别判定。"""
    if min(pm25, co2, design_pm, design_co2, acceptance_pm, acceptance_co2) < 0:
        raise ValueError("浓度和限值不可为负")
    return {
        "design": {
            "pm25_passed": pm25 <= design_pm,
            "co2_passed": co2 <= design_co2,
            "source": "GB/T 18883-2022 表1 转述，PM2.5 24小时均值、CO₂ 1小时均值",
        },
        "acceptance": {
            "pm25_passed": pm25 <= acceptance_pm,
            "co2_passed": co2 <= acceptance_co2,
            "source": "JGJ/T 440-2018 表7.3.4 转述；给定设计值时应核对适用限值",
        },
    }


def design_window_judgement(
    records: list[dict], *, pm25_limit: float = 50e-9, co2_limit: float = 0.001
) -> dict:
    """等间隔十分钟数据：按自然日 PM2.5 和逐 1 h CO₂ 均值与设计轨限值比较。

    浓度分别为 kg/m³ 和体积分数，返回各窗口最大均值和判断。缺测或不等间隔不判定。
    """
    if len(records) < 144:
        raise ValueError("至少需144个十分钟数据")
    times = [datetime.fromisoformat(r["time"]) for r in records]
    if any((b - a).total_seconds() != 600 for a, b in itertools.pairwise(times)):
        raise ValueError("设计轨时间窗要求严格十分钟间隔")
    pm = [float(x["indoor_pm"]) for x in records]
    co2 = [float(x["indoor_co2"]) for x in records]
    if min(*pm, *co2, pm25_limit, co2_limit) < 0:
        raise ValueError("浓度或限值无效")

    def max_window(values, size):
        current = sum(values[:size])
        best = current
        for index in range(size, len(values)):
            current += values[index] - values[index - size]
            best = max(best, current)
        return best / size

    days = {}
    for timestamp, value in zip(times, pm, strict=True):
        days.setdefault(timestamp.date(), []).append((timestamp, value))
    daily = [
        sum(value for _, value in rows) / 144
        for rows in days.values()
        if len(rows) == 144
        and rows[0][0].hour == 0
        and rows[0][0].minute == 0
        and rows[0][0].second == 0
    ]
    if not daily:
        raise ValueError("至少需要一个完整自然日数据")
    peak_pm = max(daily)
    peak_co2 = max_window(co2, 6)
    return {
        "pm25_max_24h": peak_pm,
        "co2_max_1h": peak_co2,
        "pm25_passed": peak_pm <= pm25_limit,
        "co2_passed": peak_co2 <= co2_limit,
        "source": "GB/T 18883-2022 3.7、4.2 表1，转述；PM2.5按自然日均值",
    }


def spot_evaluate(
    records: list[dict],
    *,
    retest_records: list[dict] | None = None,
    pm25_limit: float = 75e-9,
    co2_limit: float = 0.001,
) -> dict:
    """点检时间序列（PM2.5 为 kg/m³、CO₂ 为体积分数）及可选复测 → 验收轨状态。

    使用等间隔算术平均；首测至少45分钟，不合格时复测至少18小时。检测前关窗及
    系统运行条件由现场另行复核；此函数不凭传感器数据判定这些条件。
    """

    def assess(rows, retest):
        if not rows:
            raise ValueError("点检数据为空")
        times = [datetime.fromisoformat(r["time"]) for r in rows]
        timing = spot_monitor(times, retest=retest)
        intervals = [(b - a).total_seconds() for a, b in itertools.pairwise(times)]
        if len(set(intervals)) != 1:
            raise ValueError("算术平均要求采样间隔一致")
        pm_values = [float(r["indoor_pm"]) for r in rows]
        co_values = [float(r["indoor_co2"]) for r in rows]
        if min(*pm_values, *co_values, pm25_limit, co2_limit) < 0:
            raise ValueError("浓度不可为负")
        mean_pm = sum(pm_values) / len(pm_values)
        mean_co = sum(co_values) / len(co_values)
        return {
            "timing": timing,
            "indoor_pm": mean_pm,
            "indoor_co2": mean_co,
            "passed": mean_pm <= pm25_limit and mean_co <= co2_limit,
        }

    first = assess(records, False)
    if not first["timing"]["duration_passed"]:
        return {"status": "invalid_first", "first": first, "retest": None}
    if first["passed"]:
        return {"status": "passed", "first": first, "retest": None}
    if retest_records is None:
        return {"status": "retest_required", "first": first, "retest": None}
    retest = assess(retest_records, True)
    status = (
        "invalid_retest"
        if not retest["timing"]["duration_passed"]
        else "passed"
        if retest["passed"]
        else "failed"
    )
    return {"status": status, "first": first, "retest": retest}


def spot_monitor(times: list[datetime], *, retest: bool = False) -> dict:
    """时间点 → 采样时长和频率检查；复测时按 18 h 要求。"""
    if len(times) < 2:
        raise ValueError("至少两个时间点")
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(times)]
    if any(g <= 0 for g in gaps):
        raise ValueError("时间必须严格递增")
    duration = (times[-1] - times[0]).total_seconds()
    return {
        "duration_s": duration,
        "duration_passed": duration >= (18 * 3600 if retest else 45 * 60),
        "recommended_one_minute": all(g <= 60 for g in gaps),
        "source": "JGJ/T 440-2018 7.3.6 转述：1分钟采样为宜",
    }
