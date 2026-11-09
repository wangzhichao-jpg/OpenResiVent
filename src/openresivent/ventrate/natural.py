"""自然通风与风驱动风帽；全部物理接口采用 SI。"""

import math

import numpy as np

from openresivent.network.elements import Orifice
from openresivent.network.solver import Link, Zone, solve, wind_pressure

G = 9.81


def single_opening(cd: float, area: float, height: float, delta_t: float, mean_t: float) -> float:
    """流量系数、面积 m²、高度 m、温差 K、平均温度 K → 体积流量 m³/s。"""
    if min(cd, area, height, mean_t) <= 0 or delta_t < 0:
        raise ValueError("单开口参数无效")
    return cd * area / 3 * math.sqrt(G * height * delta_t / mean_t)


def double_opening(
    cd: float, a1: float, a2: float, height: float, delta_t: float, mean_t: float
) -> dict:
    """两个开口 m²、高差 m、温差及均温 K → 等效面积 m² 与风量 m³/s。"""
    if min(cd, a1, a2, height, mean_t) <= 0 or delta_t < 0:
        raise ValueError("双开口参数无效")
    equivalent = 1 / math.sqrt(1 / a1**2 + 1 / a2**2)
    return {
        "equivalent_area_m2": equivalent,
        "flow_m3_s": cd * equivalent * math.sqrt(2 * G * height * delta_t / mean_t),
    }


def book_single_opening(area: float, height: float, delta_t: float) -> float:
    """式(2-7)：开口面积 m²、高度 m、温差 K → 风量 m³/s。"""
    if (
        not all(math.isfinite(x) for x in (area, height, delta_t))
        or min(area, height) <= 0
        or delta_t < 0
    ):
        raise ValueError("单开口参数无效")
    return 0.04 * area * math.sqrt(delta_t * height)


def book_double_opening(a1: float, a2: float, height: float, delta_t: float) -> float:
    """式(2-8)：两孔面积 m²、高差 m、温差 K → 风量 m³/s。"""
    if (
        not all(math.isfinite(x) for x in (a1, a2, height, delta_t))
        or min(a1, a2, height) <= 0
        or delta_t < 0
    ):
        raise ValueError("双开口参数无效")
    area = 1 / math.hypot(1 / a1, 1 / a2)
    return 0.15 * area * math.sqrt(delta_t * height)


def book_opening_heights(area: float) -> dict:
    """迎风面积 m² → 临界高度 Hc 与 Hk，均为 m。"""
    if not math.isfinite(area) or area <= 0:
        raise ValueError("迎风面积必须为正")
    root = math.sqrt(area)
    return {"hc_m": 0.3 * root, "hk_m": root}


def coupled(
    a1: float,
    a2: float,
    cd: float,
    height: float,
    inside_t: float,
    outside_t: float,
    wind_speed: float = 0,
    cp1: float = 0,
    cp2: float = 0,
) -> dict:
    """两开口面积、高差 m、内外 K、风速 m/s 与风压系数 → M2 网络。"""
    from openresivent.core.psychrometrics import density

    if min(a1, a2, cd, height, inside_t, outside_t) <= 0 or wind_speed < 0:
        raise ValueError("网络参数无效")
    rho = density(outside_t, 101325)
    zones = {"outside": Zone(outside_t, fixed=True), "room": Zone(inside_t)}
    links = [
        Link(
            "outside",
            "room",
            1,
            0.5,
            element=Orifice(cd, a1),
            height=0,
            wind_pressure=wind_pressure(cp1, rho, wind_speed),
        ),
        Link(
            "room",
            "outside",
            1,
            0.5,
            element=Orifice(cd, a2),
            height=height,
            wind_pressure=-wind_pressure(cp2, rho, wind_speed),
        ),
    ]
    return solve(zones, links, tolerance=1e-11)


def metrics(turbine: float, natural: float, static: float) -> dict:
    """风帽、自然开口及静态风帽同条件风量 m³/s → 两种比例，无量纲。"""
    if turbine < 0 or natural <= 0 or static <= 0:
        raise ValueError("风量必须有效且分母为正")
    return {
        "gamma_natural": turbine / natural,
        "phi_static": turbine / static - 1,
        "paper13_gamma": turbine / static,
        "paper13_phi": turbine / static - 1,
    }


# 论文11图19：固定风速8 m/s，系统入口压力 Pa 对风量 L/s 的读图估计。
def paper11_pressure_flow(pressure: float) -> float:
    """入口压力 Pa → 风量 m³/s，仅图19 −10～10 Pa，风速固定 8 m/s。"""
    if not -10 <= pressure <= 10:
        raise ValueError("超出论文图19压力范围")
    return (
        float(
            np.interp(pressure, [-10, -5, -2.5, 0, 2.5, 5, 10], [100, 208, 260, 319, 370, 425, 545])
        )
        / 1000
    )


def paper12_cd(angle_deg: float) -> float:
    """上倾角度 0–40° → 论文12图11排量比 Q风帽/Q同径敞口。"""
    if not 0 <= angle_deg <= 40:
        raise ValueError("超出论文图11角度范围")
    return float(np.interp(angle_deg, [0, 10, 20, 30, 40], [0.80, 0.62, 0.59, 0.58, 0.55]))


def paper13_performance(
    pressure: float, wind: float, rho: float = 1.2, static_loss: float = 1.5
) -> dict:
    """论文13图6 Φ280 已发表回归；入口压力 Pa、风速 m/s、空气密度 → 风量 m³/s。

    无量纲压力 P/(0.5ρV²)=-0.347+0.539u+2.476u²，u=喉部速度/风速。
    仅在图中 u=0.1～2.3 范围内求解，不得外推；静态风帽 K=1.5。
    """
    if wind <= 0 or rho <= 0 or static_loss <= 0 or pressure < 0:
        raise ValueError("图6正压风帽参数无效")
    p = pressure / (0.5 * rho * wind**2)
    discriminant = 0.539**2 + 4 * 2.476 * (p + 0.347)
    u = (-0.539 + math.sqrt(discriminant)) / (2 * 2.476)
    if not 0.1 <= u <= 2.3:
        raise ValueError("超出论文13图6回归图示范围")
    area = math.pi * 0.28**2 / 4
    turbine = area * wind * u
    static = area * math.sqrt(2 * pressure / (rho * static_loss)) if pressure > 0 else 0
    return {
        "turbine_m3_s": turbine,
        "static_m3_s": static,
        "paper13_gamma": turbine / static if static else None,
        "phi": turbine / static - 1 if static else None,
        "dimensionless_velocity": u,
    }


def paper13_threshold(pressure: float) -> float:
    """论文13图7a Φ200 正压 Pa → φ=0 的临界风速 m/s，仅 3–30 Pa。"""
    if not 3 <= pressure <= 30:
        raise ValueError("超出论文图7a正压范围")
    return float(
        np.interp(
            pressure,
            [3, 6, 9, 10, 12, 15, 18, 21, 24, 27, 30],
            [6.5, 9, 11, 11.5, 12.7, 14.1, 15.4, 16.6, 17.8, 18.9, 20],
        )
    )


def suitability(pressure: float, wind: float) -> dict:
    """正压 Pa、风速 m/s → 对 Φ200 风帽与静态风帽比较，仅图7a边界。"""
    if wind < 0:
        raise ValueError("风速不得为负")
    threshold = paper13_threshold(pressure)
    return {
        "threshold_m_s": threshold,
        "turbine_better_than_static": wind > threshold,
        "warning": "图7a仅特定 Φ200 装置、静态风帽与入口压力；不外推其他设备。",
    }
