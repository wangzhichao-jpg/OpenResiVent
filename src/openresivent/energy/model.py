"""M5 显热/全热、旁通、滤网与控制方式框架，内核 SI。

纸面出处：吕伟华等 (2023) 第 5 页式 (1)，第 9 页式 (16)–(20)；
第 5 页表 1；孙晓雨等 (2024) 第 3 页式 (6)。默认电机效率和风机曲线
为假设，不能当作文献实测。逐时采用分段常值而非建筑动态模拟。
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

from scipy.optimize import brentq

from openresivent.core.psychrometrics import enthalpy
from openresivent.energy.weather import WeatherHour
from openresivent.network.elements import PolynomialFan


def filter_pressure(flow: float, dust_kg: float) -> float:
    """流量 m³/s、积尘 kg → Pa；吕伟华等第 5 页式 (1)，拟合量纲按 m³/h、g。"""
    if flow < 0 or dust_kg < 0:
        raise ValueError("流量和积尘不得为负")
    return 0.0199 * (flow * 3600) ** 1.3809 * 1.0269 ** (dust_kg * 1000)


def sun_filter_pressure(
    flow: float,
    dust_kg: float,
    coefficient: float = 0.018283,
    exponent: float = 1.395292,
    base: float = 1.026994,
) -> float:
    """风量 m³/s、积尘 kg 及实验回归系数 → Pa；孙晓雨等 2024 第 3 页式 (6)。

    默认系数取孙文第 6 页式 (9)；原式工程单位为 m³/h、g。
    与吕文参数对应不同实验滤网，不应混称。
    """
    if min(flow, dust_kg, coefficient) < 0 or exponent <= 0 or base < 1:
        raise ValueError("滤网回归参数无效")
    return coefficient * (flow * 3600) ** exponent * base ** (dust_kg * 1000)


def fan_curve_operating_point(
    fan: PolynomialFan, resistance: Callable[[float], float], efficiency: float
) -> dict:
    """M2 风机对象、管阻函数 Pa(Q m³/s)、机组总效率 → 工作点流量及电功率。"""
    if not 0 < efficiency <= 1 or fan.q_max <= 0:
        raise ValueError("风机效率或曲线无效")

    def objective(q):
        pressure = resistance(q)
        if pressure < 0:
            raise ValueError("风管阻力不得为负")
        return fan.flow(-pressure)[0] - q

    q = brentq(objective, 0, fan.q_max, xtol=1e-13)
    p = resistance(q)
    return {"flow_m3_s": q, "pressure_pa": p, "fan_power_w": q * p / efficiency}


def sensible_power(
    flow: float, rho: float, cp: float, delta_t: float, efficiency: float = 0
) -> float:
    """风量 m³/s、密度 kg/m³、比热 J/(kg·K)、温差 K、效率 → 处理负荷 W。"""
    if min(flow, rho, cp) < 0 or not 0 <= efficiency <= 1:
        raise ValueError("显热计算参数无效")
    return flow * rho * cp * delta_t * (1 - efficiency)


def enthalpy_power(
    flow: float,
    rho_dry: float,
    outdoor_temperature: float,
    outdoor_ratio: float,
    indoor_temperature: float,
    indoor_ratio: float,
    efficiency: float = 0,
) -> float:
    """风量 m³/s、干空气质量密度 kg/m³、温度 K、含湿量 kg/kg → 有符号全热负荷 W。

    正值为室外焓高于室内（冷负荷），密度按验收基准取干空气质量/体积，
    不是将湿空气总密度直接误认为干空气密度。
    """
    if min(flow, rho_dry) < 0 or not 0 <= efficiency <= 1:
        raise ValueError("全热计算参数无效")
    return (
        flow
        * rho_dry
        * (
            enthalpy(outdoor_temperature, outdoor_ratio)
            - enthalpy(indoor_temperature, indoor_ratio)
        )
        * (1 - efficiency)
    )


def paper_erv_efficiencies(flow: float, season: str) -> tuple[float, float]:
    """m³/s、季节 → 显热和焓效率；吕伟华等 2023 第 5 页表 1，端点外钳制。"""
    if flow < 0 or season not in ("heating", "cooling"):
        raise ValueError("换热效率输入无效")
    import numpy as np

    rates = [210, 280, 350]
    sensible = [0.825, 0.801, 0.783] if season == "heating" else [0.678, 0.640, 0.599]
    total = [0.773, 0.737, 0.712] if season == "heating" else [0.664, 0.618, 0.579]
    return float(np.interp(flow * 3600, rates, sensible)), float(
        np.interp(flow * 3600, rates, total)
    )


def paper_heat_pump_cop(temperature: float, season: str) -> float:
    """室外温度 K 和季节 → 热泵 COP；吕伟华等第 9 页式 (16)、(17)。"""
    t = temperature - 273.15
    if season not in ("heating", "cooling"):
        raise ValueError("COP 季节无效")
    value = 0.0662 * t + 2.522 if season == "heating" else -0.1119 * t + 7.44
    if value <= 0:
        raise ValueError("论文 COP 回归超出正值适用范围")
    return value


def fan_power(flow: float, specific_power: float) -> float:
    """风量 m³/s、单位风量耗功率 W/(m³/s) → W。"""
    if min(flow, specific_power) < 0:
        raise ValueError("风量或单位耗功率无效")
    return flow * specific_power


def hourly_load(
    weather: WeatherHour,
    *,
    mode: str,
    indoor_temperature: float,
    indoor_ratio: float,
    flow: float,
    rho: float = 1.2,
    cp: float = 1006,
    sensible_efficiency: float = 0,
    enthalpy_efficiency: float = 0,
    bypass: str = "none",
    minimum_difference: float = 0,
    frost: Callable[[WeatherHour], bool] | None = None,
) -> dict:
    """单小时气象和室内工况 → 热/冷负荷与回收功率 W；结霜仅为外部禁用接口。"""
    if mode not in ("heating", "cooling", "off") or bypass not in (
        "none",
        "temperature",
        "enthalpy",
    ):
        raise ValueError("季节或旁通模式无效")
    if (
        min(flow, rho, cp, minimum_difference) < 0
        or not 0 <= sensible_efficiency <= 1
        or not 0 <= enthalpy_efficiency <= 1
    ):
        raise ValueError("热回收参数无效")
    free_t = indoor_temperature - weather.temperature
    free_h = enthalpy(indoor_temperature, indoor_ratio) - enthalpy(
        weather.temperature, weather.humidity_ratio
    )
    pass_bypass = mode == "cooling" and (
        (bypass == "temperature" and free_t >= minimum_difference and free_t > 0)
        or (bypass == "enthalpy" and free_h >= minimum_difference and free_h > 0)
    )
    frost_disabled = bool(frost(weather)) if frost else False
    es = 0 if pass_bypass or frost_disabled else sensible_efficiency
    et = 0 if pass_bypass or frost_disabled else enthalpy_efficiency
    sensible = sensible_power(flow, rho, cp, free_t, es)
    total = enthalpy_power(
        flow, rho, weather.temperature, weather.humidity_ratio, indoor_temperature, indoor_ratio, et
    )
    sensible_raw = sensible_power(flow, rho, cp, free_t)
    total_raw = enthalpy_power(
        flow, rho, weather.temperature, weather.humidity_ratio, indoor_temperature, indoor_ratio
    )
    return {
        "heating_w": max(0, sensible) if mode == "heating" else 0.0,
        "cooling_w": max(0, total) if mode == "cooling" else 0.0,
        "sensible_w": sensible,
        "total_w": total,
        "recovered_w": (
            max(0, sensible_raw) * es
            if mode == "heating"
            else max(0, total_raw) * et
            if mode == "cooling"
            else 0.0
        ),
        "natural_cooling_w": max(0, sensible_raw) if pass_bypass else 0.0,
        "bypass": pass_bypass,
        "frost_disabled": frost_disabled,
    }


@dataclass(frozen=True)
class ControlConfig:
    """控制框架：风量 m³/s，阻力 Pa、积尘 kg、效率无量纲。"""

    design_flow: float = 180 / 3600  # 吕伟华等 p.3，示例
    duct_pressure: float = 50  # 吕伟华等 p.3，设计点
    filter_design_pressure: float = 140  # 同上，设计点
    pid_min_pressure: float = 100  # 吕伟华等 p.6–7
    cav_shutoff_pressure: float = 450  # 通用二次曲线假设，非论文实测
    pid_shutoff_pressure: float = 550  # 通用二次曲线假设，非论文实测
    motor_efficiency: float = 0.35  # 假设：静压功率/电功率，不代表设备实测
    filter_model: str = "lyu"  # lyu 第 5 页式 (1)；sun 第 6 页式 (9)
    fan_model: str = "quadratic_assumed"  # 或 paper_digitized，论文图4/11读图
    sun_duct_pressure: float = 140.8  # 孙文表1、350 m³/h 额定管外余压 Pa


def control_step(mode: str, dust_kg: float, config: ControlConfig | None = None) -> dict:
    """滤网积尘 kg → 风量 m³/s、风压 Pa、风机功率 W 与阀压降 Pa。"""
    c = config or ControlConfig()
    qd = c.design_flow
    if (
        mode not in ("cav", "pid", "vav")
        or min(
            qd,
            c.duct_pressure,
            c.filter_design_pressure,
            c.cav_shutoff_pressure,
            c.pid_shutoff_pressure,
            c.motor_efficiency,
        )
        <= 0
        or c.pid_min_pressure < 0
        or c.motor_efficiency > 1
        or c.filter_model not in ("lyu", "sun")
        or c.fan_model not in ("quadratic_assumed", "paper_digitized", "sun_digitized")
    ):
        raise ValueError("风机控制参数无效")

    def resistance(q):
        f = filter_pressure if c.filter_model == "lyu" else sun_filter_pressure
        return c.duct_pressure * (q / qd) ** 2 + f(q, dust_kg)

    if c.fan_model == "sun_digitized":
        if mode != "cav" or c.filter_model != "sun":
            raise ValueError("孙文读图风机仅支持 CAV 与孙文滤网")
        from openresivent.recovery.fouling import sun_figure_flow

        result = sun_figure_flow(dust_kg, duct_pressure_rated=c.sun_duct_pressure)
        result.update(
            {
                "valve_pressure_pa": 0.0,
                "fan_power_w": 130.7,
                "target_met": result["flow_m3_s"] >= qd,
                "curve_extrapolated": False,
            }
        )
        return result
    if c.fan_model == "paper_digitized" and mode == "vav":
        from openresivent.energy.fan_figures import Q_H, electrical_power, pressure

        needed = resistance(qd)
        if needed > pressure(qd, "pid"):
            raise ValueError("最高转速无法达到设计风量")
        # 相似定律：同一论文 PID 风机等效调速；仅在读图有效范围求解。
        lower = qd / (Q_H[-1] / 3600)
        upper = min(1.0, qd / (Q_H[0] / 3600))

        def residual_speed(s):
            return s * s * pressure(qd / s, "pid") - needed

        if residual_speed(lower) > 0 or residual_speed(upper) < 0:
            raise ValueError("读图曲线范围内无调速工作点")
        speed = brentq(residual_speed, lower, upper)
        power = 96.0 * electrical_power(qd / speed, "pid") / electrical_power(qd, "pid") * speed**3
        return {
            "flow_m3_s": qd,
            "pressure_pa": needed,
            "valve_pressure_pa": 0.0,
            "fan_power_w": power,
            "speed_ratio": speed,
            "target_met": True,
            "curve_extrapolated": False,
        }
    if c.fan_model == "paper_digitized" and mode in ("cav", "pid"):
        from openresivent.energy.fan_figures import solve_flow

        return solve_flow(mode, resistance, qd, c.pid_min_pressure)
    if (
        c.cav_shutoff_pressure <= c.duct_pressure + c.filter_design_pressure
        or c.pid_shutoff_pressure <= c.duct_pressure + c.filter_design_pressure + c.pid_min_pressure
    ):
        raise ValueError("风机最大压力须高于设计工作点")
    if mode == "vav":
        q = qd
        p = resistance(q)
        valve = 0
        # 理想调速；额定曲线下的相似定律决定相对转速。
        k = (c.cav_shutoff_pressure - c.duct_pressure - c.filter_design_pressure) / qd**2
        speed2 = (p + k * q * q) / c.cav_shutoff_pressure
        if speed2 > 1:
            # 超出最高转速时转为固定最高转速交点。
            q = brentq(
                lambda x: c.cav_shutoff_pressure - k * x * x - resistance(x),
                0,
                math.sqrt(c.cav_shutoff_pressure / k),
            )
            p = resistance(q)
    else:
        shutoff = c.cav_shutoff_pressure if mode == "cav" else c.pid_shutoff_pressure
        design_p = (
            c.duct_pressure
            + c.filter_design_pressure
            + (c.pid_min_pressure if mode == "pid" else 0)
        )
        k = (shutoff - design_p) / qd**2
        if mode == "pid" and shutoff - k * qd**2 >= resistance(qd) + c.pid_min_pressure:
            q = qd
            p = shutoff - k * q * q
            valve = p - resistance(q)
        else:
            valve = c.pid_min_pressure if mode == "pid" else 0
            q = brentq(
                lambda x: shutoff - k * x * x - resistance(x) - valve, 0, math.sqrt(shutoff / k)
            )
            p = resistance(q) + valve
    return {
        "flow_m3_s": q,
        "pressure_pa": p,
        "valve_pressure_pa": valve,
        "fan_power_w": q * p / c.motor_efficiency,
        "target_met": q >= qd * (1 - 1e-8),
    }


@dataclass(frozen=True)
class AnnualConfig:
    """室内设定、回收及风机；温度 K、风量 m³/s、比功率 W/(m³/s)。"""

    flow: float = 150 / 3600
    rho: float = 1.2
    cp: float = 1006
    heat_temperature: float = 293.15
    cool_temperature: float = 299.15
    heat_ratio: float = 0.006
    cool_ratio: float = 0.0105
    sensible_efficiency: float = 0.75
    enthalpy_efficiency: float = 0.6
    specific_power: float = 0.45 * 3600
    bypass: str = "none"
    minimum_difference: float = 0
    pm25_kg_m3: float = 45e-9  # 论文1 p.5 北京冬季；其他城市为假设
    capture_efficiency: float = 1.0  # 假设
    heat_cop: float = 1.0
    cool_cop: float = 1.0
    control: ControlConfig = ControlConfig()


def annual(
    weather: list[WeatherHour],
    season: Callable[[WeatherHour], str],
    *,
    config: AnnualConfig | None = None,
    mode: str = "fixed",
    reset_on_season: bool = True,
    efficiency_curve: Callable[[float, str], tuple[float, float]] | None = None,
    cop_curve: Callable[[float, str], float] | None = None,
    recovery_model: Callable | None = None,
    exhaust_flow: float | None = None,
    filter_replacement_ratio: float | None = None,
) -> dict:
    """逐时气象、季节函数 → 分季和全年能量（J）；不含围护与室内建筑负荷。"""
    config = config or AnnualConfig()
    if (
        mode not in ("fixed", "cav", "pid", "vav")
        or config.heat_cop <= 0
        or config.cool_cop <= 0
        or config.pm25_kg_m3 < 0
        or not 0 <= config.capture_efficiency <= 1
        or (exhaust_flow is not None and exhaust_flow <= 0)
        or (recovery_model is not None and exhaust_flow is None)
        or (
            filter_replacement_ratio is not None
            and (
                filter_replacement_ratio <= 1
                or mode != "cav"
                or config.control.fan_model != "sun_digitized"
            )
        )
    ):
        raise ValueError("年度运行参数无效")
    out = {
        x: {
            "ventilation_j": 0.0,
            "recovered_j": 0.0,
            "infiltration_j": 0.0,
            "fan_j": 0.0,
            "hvac_electric_j": 0.0,
            "hours": 0,
        }
        for x in ("heating", "cooling", "off")
    }
    dust = 0.0
    previous = "off"
    min_flow = math.inf
    max_flow = 0.0
    flow_sum = 0.0
    unmet_hours = 0
    extrapolated_hours = 0
    core_extrapolated_hours = 0
    core_temperature_extrapolated_hours = 0
    core_bounded_hours = 0
    replacement_count = 0
    clean_filter_pressure = (
        control_step("cav", 0, config.control)["filter_pressure_pa"]
        if filter_replacement_ratio is not None
        else None
    )
    for w in weather:
        s = season(w)
        if s not in out:
            raise ValueError("季节函数须返回 heating、cooling 或 off")
        if s == "off":
            previous = s
            continue
        if reset_on_season and s != previous:
            dust = 0.0
        previous = s
        ctrl = None if mode == "fixed" else control_step(mode, dust, config.control)
        if (
            filter_replacement_ratio is not None
            and ctrl["filter_pressure_pa"] >= clean_filter_pressure * filter_replacement_ratio
        ):
            dust = 0.0
            replacement_count += 1
            ctrl = control_step(mode, dust, config.control)
        flow = config.flow if ctrl is None else ctrl["flow_m3_s"]
        flow_sum += flow
        if ctrl is not None and not ctrl["target_met"]:
            unmet_hours += 1
        if ctrl is not None and ctrl.get("curve_extrapolated", False):
            extrapolated_hours += 1
        power = fan_power(flow, config.specific_power) if ctrl is None else ctrl["fan_power_w"]
        heat = s == "heating"
        es, et = (
            efficiency_curve(flow, s)
            if efficiency_curve
            else (config.sensible_efficiency, config.enthalpy_efficiency)
        )
        indoor_t = config.heat_temperature if heat else config.cool_temperature
        indoor_w = config.heat_ratio if heat else config.cool_ratio
        if recovery_model is not None:
            core = recovery_model(
                w.temperature, indoor_t, w.humidity_ratio, indoor_w, flow, exhaust_flow
            )
            if not core["within_physical_range"]:
                raise ValueError("换热芯体回归超出物理范围，拒绝用于年度能耗")
            if not core["within_flow_validation_range"]:
                core_extrapolated_hours += 1
            if not core.get("within_temperature_validation_range", True):
                core_temperature_extrapolated_hours += 1
            if core.get("bounded_extrapolation", False):
                core_bounded_hours += 1
            es = core["sensible_efficiency"] if core["sensible_efficiency"] is not None else 0.0
            delta_h = enthalpy(indoor_t, indoor_w) - enthalpy(w.temperature, w.humidity_ratio)
            et = (
                (
                    enthalpy(core["supply_temperature_k"], core["supply_humidity_ratio"])
                    - enthalpy(w.temperature, w.humidity_ratio)
                )
                / delta_h
                if not heat and abs(delta_h) > 1e-8
                else 0.0
            )
            if not 0 <= et <= 1:
                raise ValueError("芯体推算焓效率超出物理范围")
        cop = (
            cop_curve(w.temperature, s)
            if cop_curve
            else (config.heat_cop if heat else config.cool_cop)
        )
        if cop <= 0:
            raise ValueError("COP 须为正")
        x = hourly_load(
            w,
            mode=s,
            indoor_temperature=config.heat_temperature if heat else config.cool_temperature,
            indoor_ratio=config.heat_ratio if heat else config.cool_ratio,
            flow=flow,
            rho=config.rho,
            cp=config.cp,
            sensible_efficiency=es,
            enthalpy_efficiency=et,
            bypass=config.bypass,
            minimum_difference=config.minimum_difference,
        )
        demand = x["heating_w"] if heat else x["cooling_w"]
        infiltration = max(0.0, exhaust_flow - flow) if exhaust_flow is not None else 0.0
        inf = hourly_load(
            w,
            mode=s,
            indoor_temperature=indoor_t,
            indoor_ratio=indoor_w,
            flow=infiltration,
            rho=config.rho,
            cp=config.cp,
        )
        inf_demand = inf["heating_w"] if heat else inf["cooling_w"]
        demand += inf_demand
        cell = out[s]
        cell["infiltration_j"] += inf_demand * 3600
        cell["ventilation_j"] += demand * 3600
        cell["recovered_j"] += x["recovered_w"] * 3600
        cell["fan_j"] += power * 3600
        cell["hvac_electric_j"] += demand / cop * 3600
        cell["hours"] += 1
        dust += config.pm25_kg_m3 * flow * 3600 * config.capture_efficiency
        min_flow = min(min_flow, flow)
        max_flow = max(max_flow, flow)
    total = {
        key: sum(out[s][key] for s in ("heating", "cooling", "off"))
        for key in (
            "ventilation_j",
            "recovered_j",
            "infiltration_j",
            "fan_j",
            "hvac_electric_j",
            "hours",
        )
    }
    return {
        "seasons": out,
        "annual": total,
        "flow_min_m3_s": min_flow if min_flow < math.inf else 0.0,
        "flow_max_m3_s": max_flow,
        "flow_mean_m3_s": flow_sum / total["hours"] if total["hours"] else 0.0,
        "target_unmet_hours": unmet_hours,
        "curve_extrapolated_hours": extrapolated_hours,
        "core_extrapolated_hours": core_extrapolated_hours,
        "core_temperature_extrapolated_hours": core_temperature_extrapolated_hours,
        "core_bounded_hours": core_bounded_hours,
        "filter_replacement_count": replacement_count,
        "final_dust_kg": dust,
    }


def saving_ratio(baseline: dict, alternative: dict) -> float:
    """年 HVAC 电能与风机电能 J → 综合节能率，无量纲；书稿 4.3.3 式 4.9。"""
    b = baseline["annual"]["hvac_electric_j"] + baseline["annual"]["fan_j"]
    a = alternative["annual"]["hvac_electric_j"] + alternative["annual"]["fan_j"]
    if b <= 0:
        raise ValueError("基线总能耗须大于零")
    return (b - a) / b
