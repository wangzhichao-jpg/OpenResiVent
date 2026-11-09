"""M4 第 4 章算例分派，工程单位仅在输入层转换。"""

from openresivent.recovery.fouling import (
    dust_for_resistance_ratio,
    replacement_period,
    sun_dynamic_doubling,
    sun_dynamic_period,
)
from openresivent.recovery.frost import figure10_threshold, figure11_threshold, strategies
from openresivent.recovery.selection import assess, maintenance


def execute_recovery(module: str, d: dict) -> tuple[dict, dict]:
    """读入工程单位字典，输出 SI 结果及使用的规则包版本。"""
    if module == "m4_fouling":
        q = float(d["flow_m3_h"]) / 3600
        efficiency = float(d["capture_efficiency"])
        result = {
            "doubling_dust_kg": dust_for_resistance_ratio(float(d["pressure_ratio"]), "sun"),
            "cities": {},
            "dynamic_figure": sun_dynamic_doubling(float(d["pressure_ratio"])),
        }
        for city, concentration in d["pm10_ug_m3"].items():
            c = float(concentration) * 1e-9
            result["cities"][city] = {
                "concentration_kg_m3": c,
                "period_s": replacement_period(c, efficiency, q, ratio=float(d["pressure_ratio"])),
                "dynamic_period_s": sun_dynamic_period(
                    c, efficiency, ratio=float(d["pressure_ratio"])
                ),
                "sensitivity_s": {
                    str(scale): replacement_period(
                        c, efficiency, q * scale, ratio=float(d["pressure_ratio"])
                    )
                    for scale in (0.8, 1.2)
                },
            }
        return result, {}
    if module == "m4_frost":
        out = float(d["outdoor_c"]) + 273.15
        indoors = float(d["indoor_c"]) + 273.15
        if float(d["extract_rh"]) != 0.5:
            raise ValueError("图11仅适用于排风相对湿度50%的论文工况")
        threshold = figure11_threshold(out, float(d["outdoor_rh"]))
        result = {
            "figure10_threshold_m3_s": figure10_threshold(out, float(d["extract_rh"])),
            "figure11_threshold_m3_s": threshold,
            "figure4_reported_threshold_m3_s": 64 / 3600,
            "strategies": strategies(
                out,
                indoors,
                float(d["flow_m3_h"]) / 3600,
                threshold,
                float(d["sensible_efficiency"]),
                duration=float(d["duration_h"]) * 3600,
            ),
            "sensitivity": {str(rh): figure10_threshold(out, rh) for rh in (0.45, 0.55)},
        }
        return result, {}
    if module == "m4_assess":
        kw = {
            k: float(d[k]) for k in ("sensible_heat", "sensible_cool", "total_heat", "total_cool")
        }
        kw["specific_power"] = float(d["specific_power_w_per_m3h"]) * 3600
        return {
            "near_zero": assess("near_zero", **kw, equipment_type="sensible"),
            "general": assess("general", **kw, equipment_type="total"),
        }, {"GBT21087-2020": "2020", "GBT51350-2019": "2019"}
    if module == "m4_maintenance":
        init = float(d["initial_latent"])
        after = float(d["after_clean_latent"])
        return {
            "result": maintenance(d["core"], initial_latent=init, after_clean_latent=after),
            "sensitivity": {
                str(scale): maintenance(
                    d["core"], initial_latent=init, after_clean_latent=min(1, after * scale)
                )
                for scale in (0.95, 1.05)
            },
        }, {}
    raise ValueError("未知 M4 算例")
