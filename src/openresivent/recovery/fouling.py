"""积尘、非平衡换热和更换周期；论文 2 第 6 页式(7)–(9)。"""

import math
from itertools import pairwise

import numpy as np
from scipy.integrate import quad
from scipy.optimize import brentq

from openresivent.energy.model import ControlConfig, control_step, sun_filter_pressure


def dust_for_resistance_ratio(ratio: float, model: str = "sun") -> float:
    """相同风量时滤网阻力倍率（无量纲） → 所需积尘 kg；论文 1 式(1)或论文 2 式(9)。"""
    if ratio < 1 or model not in ("sun", "lyu"):
        raise ValueError("阻力倍率或滤网模型无效")
    return math.log(ratio) / math.log(1.026994 if model == "sun" else 1.0269) / 1000


def collected_dust(concentration: float, efficiency: float, flow: float, duration: float) -> float:
    """浓度 kg/m³、捕集率、风量 m³/s、时间 s → 积尘 kg；440 第 4.6.2 条转述。"""
    if min(concentration, flow, duration) < 0 or not 0 <= efficiency <= 1:
        raise ValueError("容尘量输入无效")
    return concentration * efficiency * flow * duration


def replacement_period(
    concentration: float, efficiency: float, flow: float, *, ratio: float = 2, model: str = "sun"
) -> float:
    """污染物浓度 kg/m³、捕集率、恒风量 m³/s → 简化更换周期 s；不模拟风量漂移。"""
    rate = collected_dust(concentration, efficiency, flow, 1)
    if rate <= 0:
        raise ValueError("积尘速率必须为正")
    return dust_for_resistance_ratio(ratio, model) / rate


def exchanger_regression(
    outdoor_t: float,
    extract_t: float,
    outdoor_w: float,
    extract_w: float,
    supply: float,
    exhaust: float,
) -> dict:
    """K、kg/kg、两侧风量 m³/s → 送风状态及显热/潜热效率。

    孙晓雨等第 6 页式(7)、(8)，拟合式内风量为 m³/h、含湿量差为 g/kg；
    允许不平衡风量。超过 0–1 的效率不裁剪，显式标记不宜外推。
    """
    if min(supply, exhaust) <= 0 or min(outdoor_w, extract_w) < 0:
        raise ValueError("换热器状态无效")
    qs, qe = supply * 3600, exhaust * 3600
    dt = extract_t - outdoor_t
    dw = (extract_w - outdoor_w) * 1000
    rise_t = math.copysign(0.383 * abs(dt) ** 1.207 * qs ** (-0.211) * qe**0.231, dt) if dt else 0.0
    rise_w = (
        math.copysign(0.760 * abs(dw) ** 1.040 * qs ** (-0.238) * qe**0.207, dw) / 1000
        if dw
        else 0.0
    )
    es = rise_t / dt if dt else None
    el = rise_w / (extract_w - outdoor_w) if dw else None
    return {
        "supply_temperature_k": outdoor_t + rise_t,
        "supply_humidity_ratio": outdoor_w + rise_w,
        "sensible_efficiency": es,
        "latent_efficiency": el,
        "within_physical_range": all(v is None or 0 <= v <= 1 for v in (es, el)),
        # 论文2第5页表2为芯体试验范围；175–438 为滤网流量范围，不可混同。
        "within_flow_validation_range": 250 <= qs <= 351 and 300 <= qe <= 351,
        "within_temperature_validation_range": (1.85 <= outdoor_t - 273.15 <= 12.28)
        if extract_t >= outdoor_t
        else (31.95 <= outdoor_t - 273.15 <= 38.05),
    }


def bounded_exchanger(
    outdoor_t: float,
    extract_t: float,
    outdoor_w: float,
    extract_w: float,
    supply: float,
    exhaust: float,
) -> dict:
    """在回归失效时将效率限制在 [0,1] 的显式保守替代，非论文公式实测。

    每次使用边界限制均通过 bounded_extrapolation 返回；对模型外工况不能声称验证。
    """
    x = exchanger_regression(outdoor_t, extract_t, outdoor_w, extract_w, supply, exhaust)
    bounded = not x["within_physical_range"]
    es = x["sensible_efficiency"]
    el = x["latent_efficiency"]
    if es is not None:
        es = min(1, max(0, es))
    if el is not None:
        el = min(1, max(0, el))
    x.update(
        {
            "sensible_efficiency": es,
            "latent_efficiency": el,
            "supply_temperature_k": outdoor_t + (extract_t - outdoor_t) * (es or 0),
            "supply_humidity_ratio": outdoor_w + (extract_w - outdoor_w) * (el or 0),
            "within_physical_range": True,
            "bounded_extrapolation": bounded,
        }
    )
    return x


def sun_figure_flow(dust_kg: float, *, duct_pressure_rated: float = 140.8) -> dict:
    """孙文图3、5读图风机及机箱阻力，加表1额定管外余压求工作点，m³/s、Pa。

    图3蓝线、图5蓝点读图（175、262、350、438 m³/h），约 ±5 Pa。
    风机并非单调，故扫描全部分段，非唯一交点或超图示范围时拒绝。
    管道余压按 Q² 假设，未调参拟合实验结果。
    """
    if dust_kg < 0 or duct_pressure_rated < 0:
        raise ValueError("积尘或额定管阻无效")
    qs = (175.0, 262.0, 350.0, 438.0)
    fan = (300.0, 338.0, 355.0, 319.0)
    box = (70.0, 95.0, 120.0, 155.0)

    def balance(qh):
        return (
            float(np.interp(qh, qs, fan) - np.interp(qh, qs, box))
            - duct_pressure_rated * (qh / 350) ** 2
            - sun_filter_pressure(qh / 3600, dust_kg)
        )

    grid = np.linspace(qs[0], qs[-1], 33)
    brackets = [(a, b) for a, b in pairwise(grid) if balance(a) * balance(b) < 0]
    exact = [x for x in grid if abs(balance(x)) < 1e-10]
    roots = [brentq(balance, a, b) for a, b in brackets] + exact
    if len(roots) != 1:
        raise ValueError("孙文读图风机在给定工况没有唯一图内工作点")
    qh = roots[0]
    return {
        "flow_m3_s": qh / 3600,
        "filter_pressure_pa": sun_filter_pressure(qh / 3600, dust_kg),
        "fan_pressure_pa": float(np.interp(qh, qs, fan)),
        "box_pressure_pa": float(np.interp(qh, qs, box)),
        "duct_pressure_pa": duct_pressure_rated * (qh / 350) ** 2,
    }


def sun_dynamic_doubling(ratio: float = 2.0) -> dict:
    """孙文图3、5与式(9)动态滤网压差达倍率的工作点；返回积尘 kg 及两组状态。"""
    if ratio <= 1:
        raise ValueError("动态压差倍率必须大于一")
    clean = sun_figure_flow(0)
    target = ratio * clean["filter_pressure_pa"]
    mass = brentq(lambda m: sun_figure_flow(m)["filter_pressure_pa"] - target, 0, 0.06, xtol=1e-12)
    dirty = sun_figure_flow(mass)
    return {
        "dust_kg": mass,
        "clean": clean,
        "dirty": dirty,
        "flow_ratio": dirty["flow_m3_s"] / clean["flow_m3_s"],
    }


def sun_dynamic_period(concentration: float, efficiency: float, *, ratio: float = 2.0) -> float:
    """颗粒物 kg/m³、捕集率 → 动态压降翻倍周期 s，论文2图3/5读图、式(9)。"""
    if concentration <= 0 or not 0 < efficiency <= 1:
        raise ValueError("浓度和捕集率必须为正")
    mass = sun_dynamic_doubling(ratio)["dust_kg"]
    integral = quad(lambda m: 1 / sun_figure_flow(m)["flow_m3_s"], 0, mass, epsrel=1e-6)[0]
    return integral / (concentration * efficiency)


def snapshot(
    dust_kg: float,
    outdoor_t: float,
    extract_t: float,
    outdoor_w: float,
    extract_w: float,
    exhaust_flow: float,
    config: ControlConfig | None = None,
) -> dict:
    """积尘 kg、温度 K、含湿量、排风 m³/s → 风量、渗透和换热器状态。"""
    if exhaust_flow <= 0:
        raise ValueError("排风须为正")
    cfg = config or ControlConfig(filter_model="sun")
    fan = control_step("cav", dust_kg, cfg)
    supply = fan["flow_m3_s"]
    core = exchanger_regression(outdoor_t, extract_t, outdoor_w, extract_w, supply, exhaust_flow)
    return {
        "supply_m3_s": supply,
        "exhaust_m3_s": exhaust_flow,
        "infiltration_m3_s": max(0, exhaust_flow - supply),
        "exfiltration_m3_s": max(0, supply - exhaust_flow),
        "fan": fan,
        "core": core,
    }
