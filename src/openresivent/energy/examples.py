"""第 4 章四城市 M5 算例；外部 TMYx 依赖显式环境变量。"""

import hashlib
import os
from dataclasses import replace
from pathlib import Path

from openresivent.energy.model import (
    AnnualConfig,
    ControlConfig,
    annual,
    paper_erv_efficiencies,
    paper_heat_pump_cop,
    saving_ratio,
)
from openresivent.energy.seasons import city_season
from openresivent.energy.weather import read_epw


def weather_files() -> dict[str, Path]:
    """从 ORV_WEATHER_DIR 解析四个城市 EPW 的绝对路径。"""
    folder = os.environ.get("ORV_WEATHER_DIR")
    if not folder:
        raise RuntimeError("未配置 ORV_WEATHER_DIR；请先准备四城市 EPW 文件")
    paths = {
        city: Path(folder) / f"{city}.epw"
        for city in ("harbin", "beijing", "shanghai", "guangzhou")
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"气象文件缺失：{path}")
    return paths


def run_energy_example(kind: str, data: dict) -> dict:
    """两类四城市算例输入工程单位，返回 SI 年累计和哈希。"""
    if kind not in ("erv", "control"):
        raise ValueError("未知 M5 算例")
    c = AnnualConfig(
        flow=float(data["flow_m3_h"]) / 3600,
        heat_temperature=float(data["heating_temperature_c"]) + 273.15,
        cool_temperature=float(data["cooling_temperature_c"]) + 273.15,
        heat_ratio=float(data["heating_humidity_ratio"]),
        cool_ratio=float(data["cooling_humidity_ratio"]),
        sensible_efficiency=float(data["sensible_efficiency"]),
        enthalpy_efficiency=float(data["enthalpy_efficiency"]),
        bypass=data["bypass"],
        pm25_kg_m3=float(data.get("pm25_ug_m3", 45)) * 1e-9,
        control=ControlConfig(
            design_flow=float(data["flow_m3_h"]) / 3600,
            cav_shutoff_pressure=float(data.get("cav_shutoff_pa", 450)),
            pid_shutoff_pressure=float(data.get("pid_shutoff_pa", 550)),
            motor_efficiency=float(data.get("motor_efficiency", 0.35)),
            fan_model=data.get("fan_model", "quadratic_assumed"),
        ),
    )
    cities = {}
    weather_hashes = {}
    for city, path in weather_files().items():
        w = read_epw(path)
        weather_hashes[city] = hashlib.sha256(path.read_bytes()).hexdigest()
        season = lambda x, city=city: city_season(city, x)
        if kind == "erv":
            base = annual(
                w, season, config=replace(c, sensible_efficiency=0, enthalpy_efficiency=0)
            )
            candidate = annual(w, season, config=c)
        else:
            opts = {
                "config": c,
                "efficiency_curve": paper_erv_efficiencies,
                "cop_curve": paper_heat_pump_cop,
            }
            base = annual(w, season, mode="cav", **opts)
            candidate = annual(w, season, mode="pid", **opts)
        b = base["annual"]["ventilation_j"]
        a = candidate["annual"]["ventilation_j"]
        cities[city] = {
            "baseline": base,
            "candidate": candidate,
            "load_reduction": (b - a) / b if b else None,
            "energy_saving": saving_ratio(base, candidate),
        }
        if city == "beijing":
            sensitivity = {}
            for scale in (0.8, 1.2):
                if kind == "erv":
                    varied = replace(
                        c,
                        sensible_efficiency=min(1, c.sensible_efficiency * scale),
                        enthalpy_efficiency=min(1, c.enthalpy_efficiency * scale),
                    )
                    alt = annual(w, season, config=varied)
                    sensitivity[str(scale)] = {
                        "load_reduction": (b - alt["annual"]["ventilation_j"]) / b
                    }
                else:
                    varied = replace(c, pm25_kg_m3=c.pm25_kg_m3 * scale)
                    opts = {
                        "config": varied,
                        "efficiency_curve": paper_erv_efficiencies,
                        "cop_curve": paper_heat_pump_cop,
                    }
                    bvar = annual(w, season, mode="cav", **opts)
                    avar = annual(w, season, mode="pid", **opts)
                    base_load = bvar["annual"]["ventilation_j"]
                    sensitivity[str(scale)] = {
                        "load_reduction": (base_load - avar["annual"]["ventilation_j"]) / base_load,
                        "energy_saving": saving_ratio(bvar, avar),
                    }
            cities[city]["sensitivity"] = sensitivity
    return {"cities": cities, "weather_sha256": weather_hashes}
