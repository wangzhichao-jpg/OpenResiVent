"""P2 书稿算例：风机曲线、户内联锁、自然渗透。

输入工程单位在此转换为 SI；示例气象、户型和设备值均为假设。
"""

from math import sqrt

from openresivent.core.psychrometrics import density
from openresivent.dwelling.makeup import minimum_makeup
from openresivent.dwelling.templates import Dwelling, calculate
from openresivent.network.elements import PolynomialFan, airtightness_coefficient
from openresivent.network.solver import Link, Zone, solve, wind_pressure


def run_fan(data: dict) -> dict:
    """二次 P-Q 曲线，自由风量 m³/h、压力 Pa → 工作点 SI。"""
    q0 = float(data["free_flow_m3_h"]) / 3600
    p0, back = float(data["shutoff_pressure_pa"]), float(data["back_pressure_pa"])
    if q0 <= 0 or p0 <= 0 or not 0 <= back <= p0:
        raise ValueError("风机曲线算例要求 0≤背压≤关闭压力")
    fan = PolynomialFan((p0, 0, -p0 / q0**2), q0)
    q, _ = fan.flow(-back)
    return {
        "flow_m3_s": q,
        "fraction": q / q0,
        "sensitivity": {str(f): sqrt(1 - min(p0, back * f) / p0) for f in (0.8, 1.0, 1.2)},
    }


def run_dwelling(data: dict) -> dict:
    """两个 n50 与补风位置方案，所有物理结果仍为 SI。"""
    results = {}
    required = {}
    for n50 in data["n50_per_h"]:
        home = Dwelling(
            int(data["bedrooms"]),
            volume=float(data["volume_m3"]),
            n50=float(n50) / 3600,
            kitchen_open=bool(data["kitchen_open"]),
            door_gap_area=float(data["door_gap_area_m2"]),
            transfer_area=float(data["transfer_area_m2"]),
            rho=float(data["density_kg_m3"]),
        )
        common = {
            "hood": float(data["hood_m3_h"]) / 3600,
            "fresh_supply": float(data["fresh_supply_m3_h"]) / 3600,
            "fresh_exhaust": float(data["fresh_exhaust_m3_h"]) / 3600,
            "threshold_pa": float(data["threshold_pa"]),
            **{
                key: data[key]
                for key in ("hood_room", "supply_room", "exhaust_room", "bath_fan_room")
            },
        }
        required[str(n50)] = {
            "mechanical": minimum_makeup(home, mode="mechanical", **common),
            "opening": minimum_makeup(home, mode="opening", **common),
        }
        results[str(n50)] = {
            "no_makeup": calculate(home, **common, opening_room="living", makeup_room="living"),
            "interlock": calculate(
                home,
                **common,
                interlock="stop_exhaust",
                opening_room="living",
                makeup_room="living",
            ),
            "opening": calculate(
                home,
                **common,
                opening_area=float(data["opening_area_m2"]),
                opening_room="living",
                makeup_room="living",
            ),
            "opening_kitchen": calculate(
                home,
                **common,
                opening_area=float(data["opening_area_m2"]),
                opening_room="kitchen",
                makeup_room="living",
            ),
            "mechanical_living": calculate(
                home,
                **common,
                mechanical_makeup=float(data["mechanical_makeup_m3_h"]) / 3600,
                makeup_room="living",
                opening_room="living",
            ),
            "mechanical_kitchen": calculate(
                home,
                **common,
                mechanical_makeup=float(data["mechanical_makeup_m3_h"]) / 3600,
                makeup_room="kitchen",
                opening_room="living",
            ),
        }
    return {"scenarios": results, "minimum_makeup": required}


def run_infiltration(data: dict) -> dict:
    """两外立面及不同高度幂律缝，稳态流入质量/室内密度计算室内容积换气次数。"""
    volume, n50 = float(data["volume_m3"]), float(data["n50_per_h"]) / 3600
    inside, outside = float(data["inside_temperature_k"]), float(data["outside_temperature_k"])
    pressure = float(data["absolute_pressure_pa"])
    height = float(data["height_m"])
    exponent = float(data["exponent"])
    coefficient = airtightness_coefficient(n50, volume, exponent) / 2
    rho_o = density(outside, pressure)
    rho_i = density(inside, pressure)
    zones = {"outside": Zone(outside, fixed=True), "inside": Zone(inside, volume=volume)}

    def compute(speed):
        links = [
            Link(
                "outside",
                "inside",
                coefficient,
                exponent,
                reference_density=rho_i,
                reference_temperature=inside,
                height=0,
                wind_pressure=wind_pressure(float(data["cp_windward"]), rho_o, speed),
            ),
            Link(
                "outside",
                "inside",
                coefficient,
                exponent,
                reference_density=rho_i,
                reference_temperature=inside,
                height=height,
                wind_pressure=wind_pressure(float(data["cp_leeward"]), rho_o, speed),
            ),
        ]
        sol = solve(zones, links, pressure_absolute=pressure, tolerance=1e-12)
        incoming = sum(max(0, flow["mass_flow"]) for flow in sol["flows"])
        return {
            "pressure_pa": sol["pressures"]["inside"],
            "air_change_per_s": incoming / rho_i / volume,
            "flows": sol["flows"],
            "mass_residual_kg_s": sol["mass_residual"],
        }

    return {
        "design": compute(float(data["wind_speed_m_s"])),
        "sensitivity": {str(v): compute(float(v)) for v in data["wind_sensitivity_m_s"]},
    }
