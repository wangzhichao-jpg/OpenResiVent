"""防霜冷角判据、论文 4 图 10 读图界限和策略比较。"""

import math

import numpy as np

from openresivent.core.psychrometrics import humidity_ratio
from openresivent.energy.model import sensible_power

# 论文4 第11页图10，室外 RH=45%、排风 20℃；按坐标网格读图，约 ±10 m³/h。
FROST_FIG10 = {
    -30: [
        (20, 124),
        (25, 80),
        (30, 70),
        (35, 64),
        (40, 60),
        (45, 57),
        (50, 54),
        (55, 51),
        (60, 49),
    ],
    -20: [(27, 363), (30, 210), (35, 145), (40, 125), (45, 110), (50, 97), (55, 89), (60, 82)],
    -14: [(38, 387), (40, 285), (45, 200), (50, 170), (55, 145), (60, 135)],
}


def cold_corner(
    outdoor_t: float,
    extract_t: float,
    outdoor_w: float,
    extract_w: float,
    flow: float,
    thermal_cross_w_k: float,
    thermal_counter_w_k: float,
    moisture_cross_kg_s: float,
    moisture_counter_kg_s: float,
    *,
    rho: float = 1.2,
    cp: float = 1006,
    surface_ratio: float = 0.5,
    pressure: float = 101325,
) -> dict:
    """K、kg/kg、m³/s、冷热侧等效传热 W/K 与传质 kg/s → 冷角状态及结霜判据。

    据李剑东等论文第 5 页式(8)–(14)，参数必须由用户提供；假定两侧平衡、
    冷角传热/传质系数为定值，surface_ratio 是室外侧换热权重，0–1。
    """
    if (
        min(flow, rho, cp, pressure) <= 0
        or min(
            thermal_cross_w_k,
            thermal_counter_w_k,
            moisture_cross_kg_s,
            moisture_counter_kg_s,
            outdoor_w,
            extract_w,
        )
        < 0
        or not 0 <= surface_ratio <= 1
    ):
        raise ValueError("冷角参数无效")
    mass = rho * flow
    te = outdoor_t + (extract_t - outdoor_t) / (
        (1 + thermal_counter_w_k / (mass * cp)) * math.exp(thermal_cross_w_k / (mass * cp))
    )
    we = outdoor_w + (extract_w - outdoor_w) / (
        (1 + moisture_counter_kg_s / mass) * math.exp(moisture_cross_kg_s / mass)
    )
    wall = surface_ratio * outdoor_t + (1 - surface_ratio) * te
    saturated = humidity_ratio(wall, 1, pressure)
    return {
        "cold_corner_temperature_k": te,
        "cold_corner_humidity_ratio": we,
        "wall_temperature_k": wall,
        "wall_saturation_ratio": saturated,
        "frost_risk": wall < 273.15 and we >= saturated,
    }


def figure10_threshold(outdoor_t: float, extract_rh: float) -> float:
    """室外温度 K、排风相对湿度 0–1 → 临界风量 m³/s；图10读图插值，不外推。"""
    t = outdoor_t - 273.15
    rh = extract_rh * 100
    temps = sorted(FROST_FIG10)
    if not temps[0] <= t <= temps[-1]:
        raise ValueError("室外温度超出图10范围")

    def at(temp):
        pts = FROST_FIG10[temp]
        if not pts[0][0] <= rh <= pts[-1][0]:
            raise ValueError("排风湿度超出对应图10曲线范围")
        return float(np.interp(rh, [p[0] for p in pts], [p[1] for p in pts]))

    if t in FROST_FIG10:
        return at(t) / 3600
    upper = next(x for x in temps if x > t)
    lower = max(x for x in temps if x < t)
    return (at(lower) + (at(upper) - at(lower)) * (t - lower) / (upper - lower)) / 3600


def figure11_threshold(outdoor_t: float, outdoor_rh: float) -> float:
    """室外温度 K、室外 RH（0–1）→ 图11阈值风量 m³/s；排风 20℃、50% RH。"""
    t = outdoor_t - 273.15
    rh = outdoor_rh * 100
    temps = (-30, -20, -14)
    if not -30 <= t <= -14 or not 20 <= rh <= 80:
        raise ValueError("室外温湿度超出图11读图范围")
    data = {
        -30: (52, 49, 46, 43, 39, 34, 30),
        -20: (84, 78, 72, 66, 59, 52, 45),
        -14: (129, 119, 107, 95, 83, 72, 60),
    }

    def at(x):
        return float(np.interp(rh, (20, 30, 40, 50, 60, 70, 80), data[x]))

    if t in data:
        return at(t) / 3600
    hi = next(x for x in temps if x > t)
    lo = max(x for x in temps if x < t)
    return (at(lo) + (at(hi) - at(lo)) * (t - lo) / (hi - lo)) / 3600


def strategies(
    outdoor_t: float,
    indoor_t: float,
    flow: float,
    threshold_flow: float,
    efficiency: float,
    *,
    rho: float = 1.2,
    cp: float = 1006,
    duration: float = 3600,
) -> dict:
    """室外室内温度 K、风量/阈值 m³/s、显热效率、时间 s → 策略功率 W 与能量 J。

    电预热至 0℃，仅为理想功率；降风量按阈值；旁通损失回收。
    风量不足的室内空气品质、结霜动力学和除霜时间均未建模。
    """
    if (
        min(flow, threshold_flow) < 0
        or min(rho, cp, duration) <= 0
        or not 0 <= efficiency <= 1
        or indoor_t <= max(outdoor_t, 273.15)
    ):
        raise ValueError("防霜策略参数无效")
    delta = indoor_t - outdoor_t
    raw = sensible_power(flow, rho, cp, delta)
    recovered = raw * efficiency
    preheat = sensible_power(flow, rho, cp, max(0, 273.15 - outdoor_t))
    reduced = min(flow, threshold_flow)
    result = {
        "preheat": {
            "supply_m3_s": flow,
            "electric_w": preheat,
            "available_recovery_w": sensible_power(flow, rho, cp, indoor_t - max(outdoor_t, 273.15))
            * efficiency,
        },
        "reduce_flow": {
            "supply_m3_s": reduced,
            "electric_w": 0.0,
            "available_recovery_w": sensible_power(reduced, rho, cp, delta) * efficiency,
        },
        "bypass": {"supply_m3_s": flow, "electric_w": 0.0, "available_recovery_w": 0.0},
        "baseline_recovery_w": recovered,
        "reduced_ventilation_warning": reduced < flow,
    }
    for name in ("preheat", "reduce_flow", "bypass"):
        item = result[name]
        item["electric_j"] = item["electric_w"] * duration
        item["recovery_j"] = item["available_recovery_w"] * duration
        item["recovery_loss_fraction"] = (
            (recovered - item["available_recovery_w"]) / recovered if recovered else None
        )
    return result
