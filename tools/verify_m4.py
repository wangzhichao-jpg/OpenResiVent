"""按论文2的分季假设和图3、5读数计算三城市积尘影响。"""

import json
import os
from dataclasses import replace
from pathlib import Path

from openresivent.energy.model import AnnualConfig, ControlConfig, annual
from openresivent.energy.weather import read_epw
from openresivent.recovery.fouling import bounded_exchanger, sun_dynamic_doubling


def main():
    """读取 ORV_WEATHER_DIR，输出 build 下 JSON，绝不写书稿。"""
    folder = Path(os.environ["ORV_WEATHER_DIR"])
    out = Path(__file__).resolve().parents[1] / "build/recovery-study/m4-trends.json"
    concentrations = {"beijing": 65, "shanghai": 49, "harbin": 68}
    values = {"dynamic": sun_dynamic_doubling(), "cities": {}}
    for city, pm10 in concentrations.items():
        full = read_epw(folder / f"{city}.epw")
        weather = [w for w in full if (w.month, w.day) >= (11, 15)] + [
            w for w in full if (w.month, w.day) <= (3, 15)
        ]
        control = ControlConfig(
            design_flow=350 / 3600, filter_model="sun", fan_model="sun_digitized"
        )
        base_config = AnnualConfig(
            flow=350 / 3600,
            heat_temperature=294.15,
            heat_ratio=0.00592,
            pm25_kg_m3=0,
            control=control,
        )
        options = {"recovery_model": bounded_exchanger, "exhaust_flow": 350 / 3600}
        clean = annual(weather, lambda _: "heating", config=base_config, **options)
        fouled = annual(
            weather,
            lambda _: "heating",
            mode="cav",
            config=replace(base_config, pm25_kg_m3=pm10 * 1e-9, capture_efficiency=0.997),
            filter_replacement_ratio=2,
            **options,
        )
        values["cities"][city] = {
            "clean": clean,
            "fouled": fouled,
            "load_increase": fouled["annual"]["ventilation_j"] / clean["annual"]["ventilation_j"]
            - 1,
        }
        print(city, values["cities"][city]["load_increase"], flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
