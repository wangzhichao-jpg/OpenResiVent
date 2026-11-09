"""P3 附加算例：读图风机调速、广州逐时新风冷负荷与无管道设备。"""

import hashlib
import os
from pathlib import Path

from openresivent.core.psychrometrics import enthalpy
from openresivent.energy.examples import weather_files
from openresivent.energy.model import (
    AnnualConfig,
    ControlConfig,
    annual,
    control_step,
    paper_erv_efficiencies,
    paper_heat_pump_cop,
    saving_ratio,
)
from openresivent.energy.seasons import city_season
from openresivent.energy.weather import read_epw
from openresivent.ventrate.air_distribution import indoor_outlets
from openresivent.ventrate.calculation import air_changes_rate, co2_flow


def vav_comparison(d: dict, weather_by_city: dict | None = None) -> dict:
    """积尘 g 输入转换 SI，比较同一论文读图风机的 PID 与理想变速。"""
    c = ControlConfig(design_flow=d["design_m3_h"] / 3600, fan_model="paper_digitized")
    rows = []
    for dust in d["dust_g"]:
        pid = control_step("pid", dust / 1000, c)
        vav = control_step("vav", dust / 1000, c)
        rows.append(
            {
                "dust_kg": dust / 1000,
                "pid": pid,
                "vav": vav,
                "saving": 1 - vav["fan_power_w"] / pid["fan_power_w"],
            }
        )
    files = weather_files() if weather_by_city is None else {}
    weather_by_city = (
        weather_by_city
        if weather_by_city is not None
        else {city: read_epw(path) for city, path in files.items()}
    )
    ac = AnnualConfig(flow=c.design_flow, control=c)
    cities = {}
    for city, weather in weather_by_city.items():
        season = lambda w, city=city: city_season(city, w)
        opts = {
            "config": ac,
            "efficiency_curve": paper_erv_efficiencies,
            "cop_curve": paper_heat_pump_cop,
        }
        pid = annual(weather, season, mode="pid", **opts)
        vav = annual(weather, season, mode="vav", **opts)
        cities[city] = {"pid": pid, "vav": vav, "energy_saving": saving_ratio(pid, vav)}
    return {
        "rows": rows,
        "cities": cities,
        "weather_sha256": {
            city: hashlib.sha256(p.read_bytes()).hexdigest() for city, p in files.items()
        },
    }


def guangzhou(d: dict, weather=None) -> dict:
    """广州气象逐时新风冷负荷 J；不包含围护或完整建筑动态负荷。"""
    sha = None
    if weather is None:
        folder = os.environ.get("ORV_WEATHER_DIR")
        if not folder:
            raise RuntimeError("未配置 ORV_WEATHER_DIR")
        path = Path(folder) / "guangzhou.epw"
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        weather = read_epw(path)
    mech_flow = d["volume_m3"] * d["mechanical_ach"] / 3600
    if mech_flow <= 0:
        raise ValueError("风量须为正")
    free_hours = 0
    potential_j = bypass_potential_j = 0.0
    no_bypass_cooling_j = bypass_cooling_j = 0.0
    h_indoor = enthalpy(d["indoor_t_k"], d["indoor_humidity_ratio"])
    efficiency = d.get("enthalpy_efficiency", 0.6)
    if not 0 <= efficiency <= 1:
        raise ValueError("焓效率无效")
    for w in weather:
        h_out = enthalpy(w.temperature, w.humidity_ratio)
        diff = h_indoor - h_out
        if diff > 0:
            free_hours += 1
            potential_j += mech_flow * d["dry_density"] * diff * (1 - efficiency) * 3600
            bypass_potential_j += mech_flow * d["dry_density"] * diff * 3600
        raw = mech_flow * d["dry_density"] * (h_out - h_indoor)
        no_bypass_cooling_j += max(0, raw * (1 - efficiency)) * 3600
        bypass_cooling_j += max(0, raw if diff > 0 else raw * (1 - efficiency)) * 3600
    return {
        "free_cooling_hours": free_hours,
        "free_cooling_without_bypass_j": potential_j,
        "free_cooling_with_bypass_j": bypass_potential_j,
        "bypass_extra_free_cooling_j": bypass_potential_j - potential_j,
        "cooling_without_bypass_j": no_bypass_cooling_j,
        "cooling_with_bypass_j": bypass_cooling_j,
        "weather_sha256": sha,
    }


def ductless(d: dict) -> dict:
    """房间面积 m²、高 m、额定风量 m³/h 和假设效率 → 校核。"""
    if (
        min(d["area_m2"], d["height_m"], d["occupants"], d["whole_area_per_person_m2"]) <= 0
        or d["devices"] < 1
    ):
        raise ValueError("房间参数无效")
    n = air_changes_rate(d["whole_area_per_person_m2"])
    area_flow = d["area_m2"] * d["height_m"] * n
    co2 = co2_flow(
        d["occupants"] * d["co2_l_h_person"] / 1000 / 3600,
        d["outdoor_ppm"] * 1e-6,
        d["limit_ppm"] * 1e-6,
    )
    demand = max(area_flow, co2)
    results = []
    for eta in d["effectiveness"]:
        if not 0 <= eta <= 1:
            raise ValueError("有效换气率须为0至1")
        effective = d["rated_m3_h"] / 3600 * eta * d["devices"]
        results.append(
            {
                "effectiveness": eta,
                "effective_flow_m3_s": effective,
                "satisfied": effective >= demand,
            }
        )
    return {
        "demand_m3_s": demand,
        "ach_flow_m3_s": area_flow,
        "co2_flow_m3_s": co2,
        "results": results,
        "one_unit_recommended": d["devices"] == 1,
        "outlet_check": indoor_outlets(d["speed_m_s"], d["layout"], d["spacing_m"], d["opposed"]),
    }
