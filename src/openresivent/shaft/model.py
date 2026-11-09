"""高层住宅稳态共用竖井；各量为 SI，参数来源和假设见 M3 理论文档。

书稿 5.3.1 给出三类风机额定点和关闭压力；书稿 5.4.1 表 5-10
给出止回阀等级。出口、门窗气密性和支管等无原始资料，属演示假设。
"""

import csv
import itertools
import math
import random
from dataclasses import dataclass, replace
from pathlib import Path

from openresivent.network.elements import (
    CheckValve,
    Duct,
    Orifice,
    PolynomialFan,
    airtightness_coefficient,
)
from openresivent.network.solver import Link, Zone, orifice_coefficient, solve, wind_pressure

# 书稿 5.3.1：额定风量 m³/h、额定静压 Pa、最大静压 Pa。
FAN_RATINGS = {"ordinary": (600, 100, 200), "common": (1080, 330, 420), "high": (1080, 800, 1000)}
# 书稿 5.4.1 的等级边界；每等级选取值为假设而非实测。
VALVE_RATES = {"good": 74, "medium": 150, "poor": 300}  # m³/(h·m²) @250 Pa


def fan_curve(kind: str) -> PolynomialFan:
    """返回 P(Q)=Pmax−kQ² 曲线；内部 Q 为 m³/s、P 为 Pa。"""
    if kind not in FAN_RATINGS:
        raise ValueError("未知油烟机类型")
    rated_h, rated_p, maximum = FAN_RATINGS[kind]
    rated = rated_h / 3600
    k = (maximum - rated_p) / rated**2
    return PolynomialFan((maximum, 0, -k), math.sqrt(maximum / k))


def valve_leakage(rate: float, diameter: float, pressure: float, exponent: float = 0.65) -> float:
    """250 Pa 漏风率 m³/(s·m²)、阀直径 m、压差 Pa → 反向风量 m³/s。"""
    if rate < 0 or diameter <= 0 or pressure < 0 or not 0 < exponent <= 1:
        raise ValueError("止回阀参数无效")
    return rate * math.pi * diameter**2 / 4 * (pressure / 250) ** exponent


def active_floors(count: int, fraction: float, distribution: str, seed: int = 0) -> list[int]:
    """楼层数、使用率、分布与种子 → 从 1 起的使用楼层列表。"""
    if count < 1 or not 0 < fraction <= 1:
        raise ValueError("楼层数和使用率无效")
    n = max(1, min(count, round(fraction * count)))
    if distribution == "lower":
        return list(range(1, n + 1))
    if distribution == "upper":
        return list(range(count - n + 1, count + 1))
    if distribution == "uniform":
        return sorted({1 + int(i * (count - 1) / (n - 1)) for i in range(n)}) if n > 1 else [1]
    if distribution == "random":
        return sorted(random.Random(seed).sample(range(1, count + 1), n))
    raise ValueError("未知楼层分布")


@dataclass(frozen=True)
class ShaftConfig:
    """楼层、截面、支管及外部条件；尺寸 m、风速 m/s、温度 K。"""

    floors: int = 6
    floor_height: float = 3.0
    width: float = 0.5
    depth: float = 0.4
    roughness: float = 0.00015
    branch_diameter: float = 0.2
    branch_length: float = 1.0
    branch_local_loss: float = 1.0
    valve_diameter: float = 0.2
    valve_forward_cd: float = 0.6
    valve_class: str = "medium"
    fan_kind: str = "ordinary"
    fraction: float = 1.0
    distribution: str = "uniform"
    seed: int = 0
    inside_temperature: float = 293.15
    outside_temperature: float = 293.15
    roof_discharge: float = 0.6
    roof_area: float = 0.2
    wind_speed: float = 0.0
    roof_cp: float = 0.0
    dwelling_volume: float = 250.0
    n50_per_s: float = 1 / 3600
    exponent: float = 0.65


@dataclass(frozen=True)
class RectangularDuct:
    """矩形段按水力直径及实际截面面积计算，与圆管相同流速和雷诺数。"""

    length: float
    width: float
    depth: float
    roughness: float
    rho: float
    viscosity: float
    local_loss: float = 0.0

    def flow(self, dp: float) -> tuple[float, float]:
        """压差 Pa → 流量 m³/s 和导数。"""
        if min(self.width, self.depth) <= 0:
            raise ValueError("截面尺寸无效")
        dh = 2 * self.width * self.depth / (self.width + self.depth)
        area = self.width * self.depth
        circ = math.pi * dh**2 / 4
        q, derivative = Duct(
            self.length, dh, self.roughness, self.local_loss, self.rho, self.viscosity
        ).flow(dp)
        return q * area / circ, derivative * area / circ


def build_network(config: ShaftConfig) -> tuple[dict, list, dict]:
    """生成节点、连接和路径索引；用于可复核建模，不含团队原始数据。"""
    c = config
    if (
        min(
            c.floor_height,
            c.width,
            c.depth,
            c.branch_diameter,
            c.branch_length,
            c.valve_diameter,
            c.roof_area,
            c.dwelling_volume,
            c.n50_per_s,
            c.inside_temperature,
            c.outside_temperature,
        )
        <= 0
        or c.roughness < 0
        or c.branch_local_loss < 0
        or c.wind_speed < 0
    ):
        raise ValueError("竖井配置无效")
    selected = set(active_floors(c.floors, c.fraction, c.distribution, c.seed))
    if c.valve_class not in VALVE_RATES:
        raise ValueError("未知止回阀等级")
    from openresivent.core.psychrometrics import density

    rho = density(c.inside_temperature, 101325)
    mu = 3.7143e-6 + 4.9286e-8 * c.inside_temperature
    rho_out = density(c.outside_temperature, 101325)
    zones = {"outside": Zone(c.outside_temperature, fixed=True)}
    links = []
    indices = {"floors": {}, "shaft": [], "active": sorted(selected)}

    def add(link):
        links.append(link)
        return len(links) - 1

    leak = airtightness_coefficient(c.n50_per_s, c.dwelling_volume, c.exponent)
    for i in range(1, c.floors + 1):
        h = (i - 0.5) * c.floor_height
        home = f"home{i}"
        shaft = f"shaft{i}"
        zones[home] = Zone(c.inside_temperature, elevation=h, volume=c.dwelling_volume)
        zones[shaft] = Zone(
            c.inside_temperature, elevation=h, volume=c.width * c.depth * c.floor_height
        )
        rec = {
            "envelope": add(
                Link(
                    "outside",
                    home,
                    leak,
                    c.exponent,
                    height=h,
                    reference_density=rho,
                    reference_temperature=c.inside_temperature,
                )
            )
        }
        forward = orifice_coefficient(c.valve_forward_cd, math.pi * c.valve_diameter**2 / 4, rho)
        leakage = VALVE_RATES[c.valve_class] / 3600 * math.pi * c.valve_diameter**2 / 4
        valve = CheckValve(0, forward, leakage, c.exponent)
        if i in selected:
            fan_end = f"fan{i}"
            duct_end = f"branch{i}"
            zones[fan_end] = Zone(c.inside_temperature, elevation=h)
            zones[duct_end] = Zone(c.inside_temperature, elevation=h)
            rec["fan"] = add(Link(home, fan_end, 1, 1, height=h, element=fan_curve(c.fan_kind)))
            rec["branch"] = add(
                Link(
                    fan_end,
                    duct_end,
                    1,
                    1,
                    height=h,
                    element=Duct(
                        c.branch_length,
                        c.branch_diameter,
                        c.roughness,
                        c.branch_local_loss,
                        rho,
                        mu,
                    ),
                )
            )
            rec["valve"] = add(Link(duct_end, shaft, 1, 1, height=h, element=valve))
        else:
            rec["valve"] = add(Link(home, shaft, 1, 1, height=h, element=valve))
        indices["floors"][i] = rec
    for i in range(1, c.floors):
        h = i * c.floor_height
        indices["shaft"].append(
            add(
                Link(
                    f"shaft{i}",
                    f"shaft{i + 1}",
                    1,
                    1,
                    height=h,
                    element=RectangularDuct(c.floor_height, c.width, c.depth, c.roughness, rho, mu),
                )
            )
        )
    roof_h = c.floors * c.floor_height
    indices["roof"] = add(
        Link(
            f"shaft{c.floors}",
            "outside",
            1,
            0.5,
            element=Orifice(c.roof_discharge, c.roof_area),
            height=roof_h,
            wind_pressure=-wind_pressure(c.roof_cp, rho_out, c.wind_speed),
        )
    )
    return zones, links, indices


def _solve(config: ShaftConfig) -> dict:
    zones, links, ids = build_network(config)
    result = solve(zones, links, tolerance=1e-10, max_iterations=150)
    flows = result["flows"]
    from openresivent.core.psychrometrics import density
    from openresivent.network.solver import G

    rho_out = density(config.outside_temperature, 101325)
    floors = []
    for i, idx in ids["floors"].items():
        q = flows[idx["valve"]]["volume_flow"]
        floors.append(
            {
                "floor": i,
                "active": i in ids["active"],
                "exhaust_m3_s": max(q, 0) if i in ids["active"] else 0.0,
                "backflow_m3_s": max(-q, 0) if i not in ids["active"] else 0.0,
                "shaft_to_outdoor_pa": result["pressures"][f"shaft{i}"]
                - (zones["outside"].pressure - rho_out * G * zones[f"shaft{i}"].elevation),
                "shaft_to_home_pa": result["pressures"][f"shaft{i}"]
                - result["pressures"][f"home{i}"],
            }
        )
    active = [x["exhaust_m3_s"] for x in floors if x["active"]]
    mean = sum(active) / len(active)
    sigma = math.sqrt(sum((q - mean) ** 2 for q in active) / len(active))
    return {
        "floors": floors,
        "_zone_pressures_pa": result["pressures"],
        "active_floors": ids["active"],
        "total_exhaust_m3_s": sum(active),
        "std_m3_s": sigma,
        "bottom_active": floors[0]["active"],
        "bottom_meets_300": floors[0]["exhaust_m3_s"] >= 300 / 3600
        if floors[0]["active"]
        else None,
        "mass_residual_kg_s": result["mass_residual"],
        "path_flows": flows,
    }


def calculate(config: ShaftConfig) -> dict:
    """计算各楼层及相同设置下去掉室外温差的热压附加风量，SI。"""
    result = _solve(config)
    baseline = _solve(replace(config, outside_temperature=config.inside_temperature))
    result["thermal_additional_m3_s"] = (
        result["total_exhaust_m3_s"] - baseline["total_exhaust_m3_s"]
    )
    return result


def scan_csv(base: ShaftConfig, dimensions: dict, path: Path) -> int:
    """楼层、截面、使用率、风机、阀等级全因子扫描并输出确定性 CSV。"""
    keys = ("floors", "sections", "fractions", "fan_kinds", "valve_classes")
    if any(k not in dimensions or not dimensions[k] for k in keys):
        raise ValueError("扫描维度不得缺失或为空")
    rows = []
    for floors, section, fraction, fan, valve in itertools.product(*(dimensions[k] for k in keys)):
        conf = replace(
            base,
            floors=int(floors),
            width=float(section[0]),
            depth=float(section[1]),
            fraction=float(fraction),
            fan_kind=fan,
            valve_class=valve,
        )
        result = calculate(conf)
        inactive = [floor for floor in result["floors"] if not floor["active"]]
        worst = max(inactive, key=lambda x: x["backflow_m3_s"]) if inactive else None
        top = result["floors"][-1]
        rows.append(
            [
                floors,
                section[0],
                section[1],
                fraction,
                {"ordinary": "普通型", "common": "常用型", "high": "高压型"}[fan],
                {"good": "良好", "medium": "中等", "poor": "差"}[valve],
                result["total_exhaust_m3_s"] * 3600,
                result["std_m3_s"] * 3600,
                result["floors"][0]["exhaust_m3_s"] * 3600 if result["bottom_active"] else None,
                result["bottom_meets_300"],
                worst["backflow_m3_s"] * 3600 if worst else None,
                worst["floor"] if worst else None,
                result["thermal_additional_m3_s"] * 3600,
                top["shaft_to_outdoor_pa"],
                top["shaft_to_home_pa"],
            ]
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "楼层数（层）",
                "竖井宽度（m）",
                "竖井深度（m）",
                "使用率（1）",
                "油烟机类型",
                "止回阀等级",
                "总排风量（m³/h）",
                "运行层风量标准差（m³/h）",
                "底层排风量（m³/h）",
                "底层是否达到300 m³/h",
                "非运行层最大倒灌风量（m³/h）",
                "最大倒灌楼层（层）",
                "热压附加风量（m³/h）",
                "顶层竖井相对同高度室外压差（Pa）",
                "顶层竖井相对同层住户压差（Pa）",
            ]
        )
        writer.writerows(rows)
    return len(rows)
