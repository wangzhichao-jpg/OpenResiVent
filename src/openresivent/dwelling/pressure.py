"""户内压力与补风的基本网络工具，单位均为 SI。

围护幂律及密度按书稿 3.1.4 和 5.3.2；本模块不代替现场燃气安全检验。
"""

from math import isfinite

from openresivent.network.elements import ConstantFlow, Orifice, PowerLaw, airtightness_coefficient
from openresivent.network.solver import Link, Zone, solve


def door_opening_force(
    width: float, height: float, handle_offset: float, pressure: float, closer: float = 0.0
) -> float:
    """门宽、高、把手距自由边 m，压差 Pa，闭门器阻力 N → 开门力 N。

    均匀压差对门轴力矩除以把手力臂；公式由力矩平衡推导，适用刚性门，
    不含锁舌、摩擦等附加力；不把本式当作已核实的规范限值。
    公式见 示例 A10，ASHRAE / NFPA 92 原文页码待核。
    """
    if width <= 0 or height <= 0 or not 0 <= handle_offset < width or closer < 0:
        raise ValueError("门及把手参数无效")
    return abs(pressure) * width * width * height / (2 * (width - handle_offset)) + closer


def single_zone(
    volume: float,
    n50_per_s: float,
    *,
    exhaust: float = 0,
    supply: float = 0,
    opening_area: float = 0,
    discharge: float = 0.6,
    rho: float = 1.2,
    exponent: float = 0.65,
    threshold_pa: float = 15,
) -> dict:
    """单区 m³、气密性 s⁻¹、送排风 m³/s、开口 m² → 压力 Pa 与各路径流量。

    孔口入流为正，固定风机为理想定流量，适合复核 A7–A9；门缝和各房间
    尚未建模。负压阈值来自书稿 5.3.2，为提示条件而非普适安全保证。
    """
    if (
        not all(
            isfinite(x)
            for x in (
                volume,
                n50_per_s,
                exhaust,
                supply,
                opening_area,
                discharge,
                rho,
                threshold_pa,
            )
        )
        or min(exhaust, supply, opening_area) < 0
        or threshold_pa <= 0
    ):
        raise ValueError("压力工况参数无效")
    coefficient = airtightness_coefficient(n50_per_s, volume, exponent)
    z = {
        "outside": Zone(293.15, fixed=True, density_kg_m3=rho),
        "home": Zone(293.15, density_kg_m3=rho, volume=volume),
    }
    links = [
        Link("outside", "home", coefficient, exponent, element=PowerLaw(coefficient, exponent))
    ]
    if opening_area:
        links.append(Link("outside", "home", 1, 0.5, element=Orifice(discharge, opening_area)))
    if exhaust:
        links.append(Link("home", "outside", 1, 1, element=ConstantFlow(exhaust)))
    if supply:
        links.append(Link("outside", "home", 1, 1, element=ConstantFlow(supply)))
    result = solve(z, links, tolerance=1e-12)
    p = result["pressures"]["home"]
    return {
        "pressure_pa": p,
        "leakage_m3_s": result["flows"][0]["volume_flow"],
        "opening_m3_s": result["flows"][1]["volume_flow"] if opening_area else 0.0,
        "negative_pressure_warning": p < -threshold_pa,
        "mass_residual_kg_s": result["mass_residual"],
    }
