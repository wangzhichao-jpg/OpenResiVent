"""算例分派，输入文件的工程单位在这里换算成 SI。"""

from dataclasses import replace
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path

import numpy as np
import yaml

from openresivent.core.case import Case
from openresivent.core.provenance import activity_data_path, parameter_data_path
from openresivent.core.psychrometrics import density
from openresivent.duct.hydraulics import (
    DuctSegment,
    balance_parallel_flows,
    fan_allowance,
    fan_operating_point,
    network,
)
from openresivent.health.risk import exposure_factor, icr, risk_category, teq
from openresivent.health.units import iur_per_ug_m3_to_per_kg_m3
from openresivent.measure.acceptance import (
    continuous_monitor,
    design_window_judgement,
    flow_deviation,
    required_homes,
    spot_evaluate,
    track_judgement,
)
from openresivent.measure.tracer import decay, read_csv, two_point
from openresivent.measure.ventilation import (
    air_change_efficiency,
    average_air_age,
    measured_flow,
    tracer_flow,
    ventilation_effectiveness,
)
from openresivent.network.elements import PolynomialFan
from openresivent.network.solver import G, Link, Zone, solve, wind_pressure
from openresivent.rules.engine import check_rule, load_pack
from openresivent.ventrate.activity import co2_generation
from openresivent.ventrate.calculation import Room, ashrae_flow, calculate_dwelling, en_co2_flow
from openresivent.ventrate.pollutant import concentration, time_to_95_percent, time_to_target

PACKS = {
    "JGJT440-2018": "jgj440_2018.yaml",
    "GBT18883-2022": "gb18883_2022.yaml",
    "GBT51350-2019": "gb51350_2019.yaml",
    "GBT21087-2020": "gb21087_2020.yaml",
    "GB50736-2012": "gb50736_2012.yaml",
    "GB55016-2021": "gb55016_2021.yaml",
}


def load_rules(ids: list[str]) -> tuple[dict, dict]:
    """读取所选规则包；输入为规则包 ID，返回规则表和版本表。"""
    rules, versions = {}, {}
    for pack_id in ids:
        if pack_id not in PACKS:
            raise ValueError(f"未知规则包：{pack_id}")
        resource = files("openresivent").joinpath("rules", "packs", PACKS[pack_id])
        pack = load_pack(resource)
        versions[pack_id] = str(pack["version"])
        rules.update({r["id"]: r for r in pack["rules"]})
    return rules, versions


def load_activity(overrides: dict | None = None) -> dict[str, float]:
    """读取活动分档表及可选体格工况；返回活动名到 CO₂ 排放量 m³/(s·人)。"""
    source = activity_data_path()
    with source.open(encoding="utf8") as stream:
        data = yaml.safe_load(stream)
    a = {**data["assumptions"], **(overrides or {})}
    return {
        item["id"]: (
            float(item["value"]) * 1e-3 / 3600
            if "value" in item
            else co2_generation(
                a["weight_kg"],
                a["sex"],
                item["met"],
                a["temperature_K"],
                a["pressure_Pa"],
                a["respiratory_quotient"],
            )
        )
        for item in data["entries"]
    }


def execute(case: Case, case_path: Path) -> tuple[dict, dict]:
    """执行算例；算例路径用于解析相对数据，返回结果和规则包版本。"""
    from openresivent.core.module_names import internal

    case = case.model_copy(update={"module": internal(case.module)})
    data = case.input
    if case.module == "duct_noise":
        from openresivent.duct.noise import noise_case

        result = noise_case(data)
        rules, versions = load_rules(["GB55016-2021"])
        result["checks"] = [
            check_rule(rules["GB55016-2021:2.1.4:sleep"], item["a_weighted_db"])
            for item in result["settings"]
        ]
        return result, versions
    if case.module == "makeup_design":
        from openresivent.dwelling.makeup import minimum_makeup
        from openresivent.dwelling.templates import Dwelling

        home = Dwelling(
            int(data["bedrooms"]),
            volume=float(data["volume_m3"]),
            n50=float(data["n50_per_h"]) / 3600,
        )
        common = {
            "hood": float(data["hood_m3_h"]) / 3600,
            "fresh_supply": float(data["fresh_supply_m3_h"]) / 3600,
            "fresh_exhaust": float(data["fresh_exhaust_m3_h"]) / 3600,
            "supply_room": "living",
            "threshold_pa": float(data.get("threshold_pa", 15)),
        }
        return {
            "mechanical": minimum_makeup(home, mode="mechanical", **common),
            "opening": minimum_makeup(home, mode="opening", **common),
        }, {}
    if case.module == "shaft":
        from openresivent.shaft.model import ShaftConfig, calculate

        result = calculate(ShaftConfig(**data))
        active = [x["exhaust_m3_s"] for x in result["floors"] if x["active"]]
        result["worst_active_exhaust_m3_s"] = min(active)
        result["max_backflow_m3_s"] = max(x["backflow_m3_s"] for x in result["floors"])
        return result, {}
    if case.module == "cfd_compare":
        from openresivent.cfd.examples import comparison

        return comparison(data), {}
    if case.module in ("p303_vav", "p303_guangzhou", "p303_ductless"):
        from openresivent.energy.p303 import ductless, guangzhou, vav_comparison

        fn = {"p303_vav": vav_comparison, "p303_guangzhou": guangzhou, "p303_ductless": ductless}[
            case.module
        ]
        return fn(data), ({"JGJT440-2018": "2018"} if case.module == "p303_ductless" else {})
    if case.module == "product_test":
        from openresivent.measure.product import (
            exchange_efficiency,
            fan_law,
            purification_efficiency,
            specific_power,
        )

        d = data
        return {
            "exchange": exchange_efficiency(
                d["supply_mass_kg_s"],
                d["exhaust_mass_kg_s"],
                d["outdoor_t_k"],
                d["exhaust_t_k"],
                d["supply_t_k"],
                d["outdoor_w"],
                d["exhaust_w"],
                d["supply_w"],
            ),
            "fan": fan_law(
                d["fan_flow_m3_h"] / 3600, d["fan_pressure_pa"], d["fan_power_w"], d["speed_ratio"]
            ),
            "specific": specific_power(d["test_flow_m3_h"] / 3600, d["test_power_w"]),
            "purification": purification_efficiency(
                d["test_flow_m3_h"] / 3600, d["pm25_efficiency"], d["test_power_w"], d["kind"]
            ),
        }, {"JGJT440-2018": "2018"}
    if case.module.startswith("p3_"):
        from openresivent.ventrate.p3_examples import run

        return run(case.module, data), {}
    if case.module.startswith("m4_"):
        from openresivent.recovery.examples import execute_recovery

        return execute_recovery(case.module, data)
    if case.module in ("energy_erv", "energy_control"):
        from openresivent.energy.examples import run_energy_example

        return run_energy_example("erv" if case.module == "energy_erv" else "control", data), {}
    if case.module in ("p2_fan", "p2_dwelling", "p2_infiltration"):
        from openresivent.core.p2_examples import run_dwelling, run_fan, run_infiltration

        fn = {"p2_fan": run_fan, "p2_dwelling": run_dwelling, "p2_infiltration": run_infiltration}[
            case.module
        ]
        return fn(data), {}
    if case.module == "duct_network":
        with parameter_data_path("duct_fittings.yaml").open(encoding="utf8") as stream:
            fitting_rows = yaml.safe_load(stream)["entries"]
        fitting_coefficients = {row["id"]: float(row["zeta"]) for row in fitting_rows}
        segments = {
            item["name"]: DuctSegment(
                name=item["name"],
                length=float(item["length_m"]),
                flow=float(item["flow_m3_h"]) / 3600,
                roughness=float(item["roughness_m"]),
                diameter=float(item["diameter_m"]) if "diameter_m" in item else None,
                width=float(item["width_m"]) if "width_m" in item else None,
                height=float(item["height_m"]) if "height_m" in item else None,
                local_zeta=float(item.get("local_zeta", 0))
                + sum(fitting_coefficients[key] for key in item.get("fittings", [])),
                role=item.get("role", "branch"),
            )
            for item in data["segments"]
        }
        result = network(
            segments,
            data["routes"],
            float(data["density_kg_m3"]),
            float(data["kinematic_viscosity_m2_s"]),
        )
        total_flow = float(data["design_flow_m3_h"]) / 3600
        result["balanced"] = balance_parallel_flows(
            segments,
            data["routes"],
            total_flow,
            float(data["density_kg_m3"]),
            float(data["kinematic_viscosity_m2_s"]),
        )
        result["fan_allowance"] = fan_allowance(total_flow, result["pressure_pa"], flow_unit="m3/s")
        result["sensitivity_local_zeta"] = {
            str(scale): network(
                {
                    name: replace(segment, local_zeta=segment.local_zeta * scale)
                    for name, segment in segments.items()
                },
                data["routes"],
                float(data["density_kg_m3"]),
                float(data["kinematic_viscosity_m2_s"]),
            )["pressure_pa"]
            for scale in (0.8, 1.0, 1.2)
        }
        if "fan" in data:
            fan_data = data["fan"]
            qmax = float(fan_data["free_flow_m3_h"]) / 3600
            pressure = float(fan_data["shutoff_pressure_pa"])
            fan = PolynomialFan((pressure, 0.0, -pressure / qmax**2), qmax)
            result["fan_operating_point"] = fan_operating_point(
                fan,
                segments,
                data["routes"][result["critical_route"]],
                float(data["density_kg_m3"]),
                float(data["kinematic_viscosity_m2_s"]),
            )
        return result, {"JGJT440-2018": "2018"}
    if case.module == "ventrate":
        ids = case.meta.rules or ["JGJT440-2018", "GBT18883-2022"]
        rules, versions = load_rules(ids)
        if "JGJT440-2018" not in ids:
            raise ValueError("全户法需要启用 JGJT440-2018")
        total = float(data.get("occupants", data.get("default_occupants", 3.2)))
        activity = load_activity(data.get("activity_person"))

        def emission(room):
            return (
                sum(
                    float(x["ef_mg_m2_h"]) * float(x["area_m2"])
                    for x in room.get("hcho_materials", [])
                )
                * 1e-6
                / 3600
            )

        bedrooms = [
            Room(
                float(x["area_m2"]),
                float(x["height_m"]),
                float(x["occupants"]),
                activity[x.get("activity", "sedentary")],
                emission(x),
            )
            for x in data["bedrooms"]
        ]
        room = data["living"]
        living = Room(
            float(room["area_m2"]), float(room["height_m"]), total, hcho_generation=emission(room)
        )
        b_enabled = "GBT18883-2022" in ids or "GBT51350-2019" in ids
        result = calculate_dwelling(
            float(data["area_m2"]),
            float(data["height_m"]),
            total,
            bedrooms,
            living,
            include_people=b_enabled,
            outdoor=float(data.get("outdoor_ppm", 400)) * 1e-6,
            limit=float(data.get("limit_ppm", 1000)) * 1e-6,
            allowance=float(data.get("allowance", 0.05)),
            hcho_outdoor=float(data.get("hcho_outdoor_mg_m3", 0.01)) * 1e-6,
            hcho_limit=float(data.get("hcho_limit_mg_m3", 0.08)) * 1e-6,
            hcho_whole_generation=emission(data),
        )
        if "hcho_sensitivity" in data:
            result["hcho_sensitivity"] = {}
            for scale in data["hcho_sensitivity"]:
                scale = float(scale)
                if scale < 0:
                    raise ValueError("敏感性系数不能为负")
                varied = calculate_dwelling(
                    float(data["area_m2"]),
                    float(data["height_m"]),
                    total,
                    [replace(x, hcho_generation=x.hcho_generation * scale) for x in bedrooms],
                    replace(living, hcho_generation=living.hcho_generation * scale),
                    include_people=b_enabled,
                    outdoor=float(data.get("outdoor_ppm", 400)) * 1e-6,
                    limit=float(data.get("limit_ppm", 1000)) * 1e-6,
                    allowance=float(data.get("allowance", 0.05)),
                    hcho_outdoor=float(data.get("hcho_outdoor_mg_m3", 0.01)) * 1e-6,
                    hcho_limit=float(data.get("hcho_limit_mg_m3", 0.08)) * 1e-6,
                    hcho_whole_generation=emission(data) * scale,
                )
                result["hcho_sensitivity"][str(scale)] = varied["design"]
        if "hcho_example_ef_mg_m2_h" in data:
            example_ef = float(data["hcho_example_ef_mg_m2_h"])
            materials = data["bedrooms"][0].get("hcho_materials", [])
            if example_ef < 0 or len(materials) != 1:
                raise ValueError("甲醛对照情形需要一项材料及非负散发率")
            example_generation = example_ef * float(materials[0]["area_m2"]) * 1e-6 / 3600
            difference = (
                float(data.get("hcho_limit_mg_m3", 0.08))
                - float(data.get("hcho_outdoor_mg_m3", 0.01))
            ) * 1e-6
            if difference <= 0:
                raise ValueError("甲醛限值必须高于背景浓度")
            example_d = example_generation / difference
            example_room = dict(result["bedrooms"][0])
            example_room["D"] = example_d
            example_room["selected"] = max(
                v for k, v in example_room.items() if k in ("A", "B", "C", "D") and v is not None
            )
            result["hcho_example"] = example_room
        bedroom_count = sum(x.occupants for x in bedrooms)
        generation = (
            sum(x.occupants * x.co2_per_person for x in bedrooms) / bedroom_count
            if bedroom_count
            else activity["sedentary"]
        ) * total
        result["international"] = {
            "ashrae_m3_s": ashrae_flow(float(data["floor_area_m2"]), len(bedrooms)),
            "en_generation_m3_s": generation,
            "en_m3_s": {c: en_co2_flow(generation, c) for c in ["I", "II", "III"]},
        }
        result["checks"] = [
            check_rule(
                rules["JGJT440-2018:4.2.3"],
                result["design"],
                calculated_limit=max(result["whole_A"], result["room_total"]),
            ),
            check_rule(rules["JGJT440-2018:5.2.1"], float(data.get("allowance", 0.05))),
        ]
        if b_enabled:
            selected_b = []
            for pack, key in [
                ("GBT18883-2022", "GBT18883-2022:4.2:outdoor_air"),
                ("GBT51350-2019", "GBT51350-2019:4.0.2"),
            ]:
                if pack in ids:
                    selected_b.append(pack)
                    result["checks"].append(check_rule(rules[key], result["design"] / total))
            result["sources"]["B"] = " / ".join(selected_b)
        for room in result["bedrooms"]:
            result["checks"].append(
                check_rule(
                    rules["JGJT440-2018:4.2.2"],
                    room["selected"],
                    calculated_limit=max(room["A"], room["C"]),
                )
            )
        result["checks"].append(
            check_rule(
                rules["JGJT440-2018:4.2.1"], result["design"], calculated_limit=result["whole_A"]
            )
        )
        result["enabled_packs"] = ids
        if "noise" in data:
            from openresivent.duct.noise import noise_case

            result["noise"] = noise_case(data["noise"])
            noise_rules, noise_versions = load_rules(["GB55016-2021"])
            result["noise"]["checks"] = [
                check_rule(noise_rules["GB55016-2021:2.1.4:sleep"], row["a_weighted_db"])
                for row in result["noise"]["settings"]
            ]
            versions.update(noise_versions)
        return result, versions
    if case.module == "tracer":
        csv_path = (case_path.parent / data["csv"]).resolve()
        columns = read_csv(csv_path)
        background = float(data["background"])
        points = {
            name: decay(columns["time_s"], values, background)
            for name, values in columns.items()
            if name != "time_s"
        }
        return {
            "two_point_s_1": two_point(
                float(data["two_point"]["initial"]),
                float(data["two_point"]["final"]),
                background,
                float(data["two_point"]["elapsed_s"]),
            ),
            "points": points,
            "csv_sha256": __import__("hashlib").sha256(csv_path.read_bytes()).hexdigest(),
        }, {}
    if case.module == "transient":
        volume = float(data["volume_m3"])
        flow = float(data["flow_m3_h"]) / 3600
        outdoor = float(data["outdoor_ug_m3"]) * 1e-9
        initial = float(data["initial_ug_m3"]) * 1e-9
        generation = float(data.get("generation_ug_h", 0)) * 1e-9 / 3600
        elapsed = float(data["elapsed_h"]) * 3600
        if flow <= 0 or volume <= 0:
            raise ValueError("风量和容积须为正")
        steady = outdoor + generation / flow
        target = float(data["target_ug_m3"]) * 1e-9
        return {
            "concentration_kg_m3": concentration(
                initial, outdoor, generation, flow, volume, elapsed
            ),
            "steady_kg_m3": steady,
            "target_time_s": time_to_target(initial, steady, target, flow / volume),
            "time_95_s": time_to_95_percent(flow / volume),
        }, {}
    if case.module == "health_pah":
        data_path = parameter_data_path("pah_tef.yaml")
        with data_path.open(encoding="utf8") as stream:
            table = yaml.safe_load(stream)
        factors = {entry["id"]: float(entry["value"]) for entry in table["entries"]}
        values = {key: float(value) * 1e-12 for key, value in data["concentrations_ng_m3"].items()}
        equivalent = teq(values, factors)
        with parameter_data_path("exposure_defaults.yaml").open(encoding="utf8") as stream:
            default_rows = yaml.safe_load(stream)["entries"]
        defaults = {row["id"]: row["value"] for row in default_rows}
        risk_factor = exposure_factor(
            float(data.get("hours_day", defaults["hours_day"])),
            float(data.get("days_year", defaults["days_year"])),
            float(data.get("years", defaults["years"])),
            float(data.get("averaging_years", defaults["averaging_years"])),
        )
        unit_risk = iur_per_ug_m3_to_per_kg_m3(float(data["iur_per_ug_m3"]))
        risk = icr(equivalent, unit_risk, risk_factor)
        sensitivity = {
            str(s): icr(equivalent * float(s), unit_risk, risk_factor)
            for s in data.get("sensitivity", [1])
        }
        return {
            "teq_kg_m3": equivalent,
            "tef_used": {name: factors[name] for name in values},
            "exposure_factor": risk_factor,
            "icr": risk,
            "risk_category": risk_category(risk),
            "sensitivity": sensitivity,
        }, {}
    if case.module == "air_age":
        if "csv" in data:
            readings = read_csv((case_path.parent / data["csv"]).resolve())
            ages = [
                decay(readings["time_s"], concentrations, float(data.get("background", 0)))[
                    "local_age"
                ]
                for name, concentrations in readings.items()
                if name != "time_s"
            ]
        else:
            ages = data["ages_s"]
        avg = average_air_age(ages, data["volumes_m3"])
        result = {
            "local_ages_s": ages,
            "average_age_s": avg,
            "efficiency": air_change_efficiency(float(data["nominal_age_s"]), avg),
        }
        if "room_concentration" in data:
            result["ventilation_effectiveness"] = ventilation_effectiveness(
                float(data["exhaust_concentration"]),
                float(data["supply_concentration"]),
                float(data["room_concentration"]),
            )
        return result, {}
    if case.module == "injection":
        indoor, outdoor = float(data["indoor_ppm"]) * 1e-6, float(data["outdoor_ppm"]) * 1e-6
        # 同温同压下示踪气体体积分率可与注入体积流量相除。
        constant = tracer_flow(float(data["injection_l_min"]) * 1e-3 / 60, indoor, outdoor)
        controlled = tracer_flow(
            float(data["controlled_injection_l_min"]) * 1e-3 / 60, indoor, outdoor
        )
        return {"injection_flow_m3_s": constant, "controlled_flow_m3_s": controlled}, {}
    if case.module == "airflow_measure":
        return {
            "duct_m3_s": measured_flow(
                float(data["duct_velocity_m_s"]), float(data["duct_area_m2"])
            ),
            "terminal_m3_s": measured_flow(
                float(data["terminal_velocity_m_s"]),
                float(data["terminal_area_m2"]),
                float(data["terminal_coefficient"]),
            ),
        }, {}
    if case.module == "acceptance":
        records = data["records"]
        # 输入 CSV/YAML 数值为 μg/m³ 和 ppm，内核转为 kg/m³ 和体积分数。
        converted = [
            {
                "time": r["time"],
                "outdoor_pm": float(r["outdoor_pm_ug_m3"]) * 1e-9,
                "indoor_pm": float(r["indoor_pm_ug_m3"]) * 1e-9,
                "indoor_co2": float(r["indoor_co2_ppm"]) * 1e-6,
            }
            for r in records
        ]
        monitoring = continuous_monitor(
            converted, pm25_removal=bool(data.get("pm25_removal", True))
        )
        tracks = track_judgement(monitoring["indoor_pm"], monitoring["indoor_co2"])
        tracks["design"] = design_window_judgement(converted)

        def convert_spot(rows):
            return [
                {
                    "time": r["time"],
                    "indoor_pm": float(r["indoor_pm_ug_m3"]) * 1e-9,
                    "indoor_co2": float(r["indoor_co2_ppm"]) * 1e-6,
                }
                for r in rows
            ]

        first = convert_spot(data["spot_records"])
        retest = (
            convert_spot(data["retest_records"]) if data.get("retest_records") is not None else None
        )
        return {
            "continuous": monitoring,
            "tracks": tracks,
            "spot": spot_evaluate(first, retest_records=retest),
            "total_flow": flow_deviation(
                float(data["total_design_m3_h"]) / 3600, float(data["total_measured_m3_h"]) / 3600
            ),
            "terminal_flow": flow_deviation(
                float(data["terminal_design_m3_h"]) / 3600,
                float(data["terminal_measured_m3_h"]) / 3600,
                terminal=True,
            ),
            "required_homes": required_homes(int(data["total_homes"])),
        }, {"JGJT440-2018": "2018", "GB55015-2021": "2021"}
    if case.module == "acceptance_synthetic":
        start = datetime.fromisoformat(data["start"])
        random = np.random.default_rng(int(data["seed"]))
        records = []
        for index in range(30 * 144):
            day = index // 144
            outside = float(
                data["outdoor_high_ug_m3"]
                if day in data["worst_day_indexes"]
                else data["outdoor_base_ug_m3"]
            )
            inside = float(data["indoor_base_ug_m3"]) + float(
                random.normal(0, float(data["noise_std_ug_m3"]))
            )
            records.append(
                {
                    "time": (start + timedelta(minutes=10 * index)).isoformat(),
                    "outdoor_pm": outside * 1e-9,
                    "indoor_pm": inside * 1e-9,
                    "indoor_co2": float(data["co2_ppm"]) * 1e-6,
                }
            )
        monitoring = continuous_monitor(records)
        judgement = track_judgement(monitoring["indoor_pm"], monitoring["indoor_co2"])
        judgement["design"] = design_window_judgement(records)
        spot_records = [
            {
                "time": (start + timedelta(minutes=i)).isoformat(),
                "indoor_pm": float(data["indoor_base_ug_m3"]) * 1e-9,
                "indoor_co2": float(data["co2_ppm"]) * 1e-6,
            }
            for i in range(int(data["spot_duration_minutes"]) + 1)
        ]
        spot = spot_evaluate(spot_records)
        return {
            "continuous": monitoring,
            "tracks": judgement,
            "spot": spot,
            "total_flow": flow_deviation(
                float(data["total_design_m3_h"]) / 3600, float(data["total_measured_m3_h"]) / 3600
            ),
            "terminal_flow": flow_deviation(
                float(data["terminal_design_m3_h"]) / 3600,
                float(data["terminal_measured_m3_h"]) / 3600,
                terminal=True,
            ),
            "required_homes": required_homes(int(data["total_homes"])),
        }, {"JGJT440-2018": "2018", "GB55015-2021": "2021"}
    if case.module == "network":
        absolute = float(data.get("pressure_pa", 101325))
        zones = {
            name: Zone(
                temperature=float(z["temperature_k"]),
                pressure=float(z.get("pressure_pa", 0)),
                elevation=float(z.get("reference_height_m", 0)),
                volume=float(z.get("volume_m3", 1)),
                fixed=bool(z.get("fixed", False)),
                density_kg_m3=float(z["density_kg_m3"]) if "density_kg_m3" in z else None,
            )
            for name, z in data["zones"].items()
        }
        links = []
        for item in data["links"]:
            if "area_m2" in item:
                coefficient = 1.0
                power = 0.5
                from openresivent.network.elements import Orifice

                element = Orifice(float(item["discharge"]), float(item["area_m2"]))
            else:
                coefficient, power = float(item["coefficient"]), float(item["power"])
                element = None
            wind = wind_pressure(
                float(item.get("cp", 0)),
                float(item.get("wind_density", 1.2)),
                float(data.get("wind_speed_m_s", 0)),
            )
            links.append(
                Link(
                    item["start"],
                    item["end"],
                    coefficient,
                    power,
                    float(item.get("height_m", 0)),
                    wind,
                    element=element,
                    reference_density=float(item["reference_density"])
                    if "reference_density" in item
                    else None,
                    reference_temperature=float(item["reference_temperature_k"])
                    if "reference_temperature_k" in item
                    else None,
                )
            )
        result = solve(zones, links, pressure_absolute=absolute)
        if "stack" in data:
            stack = data["stack"]
            inside, outside = zones[stack["inside"]], zones[stack["outside"]]
            rho_inside = density(inside.temperature, absolute)
            rho_outside = density(outside.temperature, absolute)
            gradient = G * (rho_outside - rho_inside)
            p = result["pressures"][stack["inside"]] - outside.pressure
            result["stack"] = {
                "total_pressure_pa": abs(gradient * float(stack["height_m"])),
                "neutral_height_m": -p / gradient if gradient else None,
                "gradient_pa_m": gradient,
            }
            result["stack"]["simplified_pa"] = (
                0.04 * float(stack["height_m"]) * abs(inside.temperature - outside.temperature)
            )
            if len(links) == 2:
                result["stack"]["opening_sensitivity"] = {}
                for factor in (0.8, 1.2):
                    varied = [
                        links[0],
                        replace(
                            links[1],
                            element=replace(links[1].element, area=links[1].element.area * factor),
                        )
                        if links[1].element is not None
                        else replace(links[1], coefficient=links[1].coefficient * factor),
                    ]
                    res = solve(zones, varied, pressure_absolute=absolute, tolerance=1e-11)
                    result["stack"]["opening_sensitivity"][str(factor)] = (
                        -(res["pressures"][stack["inside"]] - outside.pressure) / gradient
                        if gradient
                        else None
                    )
        return result, {}
    raise ValueError(f"不支持的模块：{case.module}")
