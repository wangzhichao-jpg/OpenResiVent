"""P3 五个书稿算例；SI 求解。"""

from openresivent.ventrate.air_distribution import indoor_outlets, jet, outdoor_intake
from openresivent.ventrate.natural import (
    coupled,
    double_opening,
    metrics,
    paper11_pressure_flow,
    paper12_cd,
    paper13_performance,
    single_opening,
    suitability,
)


def run(module: str, d: dict) -> dict:
    """接受算例数据并输出 SI 结果。"""
    if module == "p3_natural":
        single = single_opening(
            d["cd"], d["single_area_m2"], d["opening_height_m"], d["delta_t_k"], d["mean_t_k"]
        )
        double = double_opening(
            d["cd"], d["a1_m2"], d["a2_m2"], d["height_m"], d["delta_t_k"], d["mean_t_k"]
        )
        both = coupled(
            d["a1_m2"],
            d["a2_m2"],
            d["cd"],
            d["height_m"],
            d["inside_t_k"],
            d["outside_t_k"],
            d["wind_m_s"],
            d["cp1"],
            d["cp2"],
        )
        thermal = coupled(
            d["a1_m2"], d["a2_m2"], d["cd"], d["height_m"], d["inside_t_k"], d["outside_t_k"]
        )
        return {
            "single_m3_s": single,
            "double": double,
            "thermal_network": thermal,
            "coupled_network": both,
            "book_single": 0.04 * d["single_area_m2"] * d["delta_t_k"] * d["opening_height_m"],
            "book_double": 0.15 * d["a1_m2"] * d["delta_t_k"] * d["height_m"],
            "sensitivity": {
                str(f): single_opening(
                    d["cd"] * f,
                    d["single_area_m2"],
                    d["opening_height_m"],
                    d["delta_t_k"],
                    d["mean_t_k"],
                )
                for f in (0.8, 1.2)
            },
        }
    if module == "p3_jet":
        return {
            "jet": jet(
                d["speed_m_s"],
                d["diameter_m"],
                d["turbulence"],
                d["distance_m"],
                d["temperature_difference_k"],
                d["target_m_s"],
            ),
            "check": indoor_outlets(d["speed_m_s"], d["layout"], d["spacing_m"], d["opposed"]),
            "sensitivity": {
                str(f): jet(
                    d["speed_m_s"],
                    d["diameter_m"],
                    d["turbulence"] * f,
                    d["distance_m"],
                    d["temperature_difference_k"],
                    d["target_m_s"],
                )["throw_m"]
                for f in (0.8, 1.2)
            },
        }
    if module == "p3_stack":
        return {
            "network": coupled(
                d["a1_m2"], d["a2_m2"], d["cd"], d["height_m"], d["inside_t_k"], d["outside_t_k"]
            ),
            "sensitivity": {
                str(f): coupled(
                    d["a1_m2"] * f,
                    d["a2_m2"],
                    d["cd"],
                    d["height_m"],
                    d["inside_t_k"],
                    d["outside_t_k"],
                )["flows"][0]["volume_flow"]
                for f in (0.8, 1.2)
            },
        }
    if module == "p3_cap":
        return {
            "metrics": metrics(d["turbine_m3_s"], d["natural_m3_s"], d["static_m3_s"]),
            "suitability": suitability(d["pressure_pa"], d["wind_m_s"]),
            "paper11_flow_m3_s": paper11_pressure_flow(d["paper11_pressure_pa"]),
            "paper12_cd": paper12_cd(d["angle_deg"]),
            "paper13_phi280": paper13_performance(d["pressure_pa"], d["wind_m_s"]),
            "sensitivity": {str(p): suitability(p, d["wind_m_s"]) for p in (6, 10, 15)},
        }
    if module == "p3_intake":
        return {
            "check": outdoor_intake(
                d["source"],
                d["horizontal_m"],
                d["vertical_m"],
                intake_below=d["intake_below"],
                layout=d["layout"],
                same_direction=d["same_direction"],
                ground_clearance=d["ground_m"],
                green=d["green"],
            ),
            "sensitivity": {
                str(v): outdoor_intake(
                    d["source"],
                    v,
                    d["vertical_m"],
                    intake_below=d["intake_below"],
                    layout=d["layout"],
                    same_direction=d["same_direction"],
                    ground_clearance=d["ground_m"],
                    green=d["green"],
                )["pollution_passed"]
                for v in (1.2, 1.5, 1.8)
            },
        }
    raise ValueError("未知算例")
