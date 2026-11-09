"""产品检测数据处理；输入输出采用 SI，示例不替代型式检验。"""

from openresivent.core.psychrometrics import enthalpy


def exchange_efficiency(
    supply_mass: float,
    exhaust_mass: float,
    outdoor_t: float,
    exhaust_t: float,
    supply_t: float,
    outdoor_w: float,
    exhaust_w: float,
    supply_w: float,
) -> dict:
    """干空气质量流量 kg/s，温度 K，含湿量 kg/kg → 显热、潜热及全热效率。

    按任务指定的最小干空气流量为分母的最大可传递量归一化，关联 ASHRAE 84 / EN 308；
    不含泄漏、平衡校正或凝结修正，不能替代标准完整试验。
    """
    if min(supply_mass, exhaust_mass) <= 0 or min(outdoor_w, exhaust_w, supply_w) < 0:
        raise ValueError("流量和含湿量无效")
    minimum = min(supply_mass, exhaust_mass)
    delta_t = exhaust_t - outdoor_t
    delta_w = exhaust_w - outdoor_w
    ho = enthalpy(outdoor_t, outdoor_w)
    he = enthalpy(exhaust_t, exhaust_w)
    hs = enthalpy(supply_t, supply_w)
    if delta_t == 0 or delta_w == 0 or he == ho:
        raise ValueError("入口状态差为零，效率未定义")
    factor = supply_mass / minimum
    return {
        "sensible": factor * (supply_t - outdoor_t) / delta_t,
        "latent": factor * (supply_w - outdoor_w) / delta_w,
        "total": factor * (hs - ho) / (he - ho),
        "minimum_dry_air_kg_s": minimum,
    }


def fan_law(flow: float, pressure: float, power: float, speed_ratio: float) -> dict:
    """流量 m³/s、压力 Pa、功率 W、转速比 → 相似风机新工况（SI）。"""
    if min(flow, pressure, power, speed_ratio) <= 0:
        raise ValueError("风机工况无效")
    return {
        "flow_m3_s": flow * speed_ratio,
        "pressure_pa": pressure * speed_ratio**2,
        "power_w": power * speed_ratio**3,
        "speed_ratio": speed_ratio,
    }


def specific_power(flow: float, power: float) -> dict:
    """体积流量 m³/s、功率 W → W/(m³/h) 和 SFP W/(m³/s)。"""
    if flow <= 0 or power < 0:
        raise ValueError("风量或功率无效")
    return {"w_per_m3_h": power / (flow * 3600), "sfp_w_per_m3_s": power / flow}


def purification_efficiency(flow: float, efficiency: float, power: float, kind: str) -> dict:
    """风量 m³/s、一次通过效率 0–1、功率 W、流型 → 净化能效与分级。"""
    if flow <= 0 or power <= 0 or not 0 <= efficiency <= 1 or kind not in ("single", "dual"):
        raise ValueError("净化能效参数无效")
    value = flow * 3600 * efficiency / power
    saving, qualified = (5.0, 2.0) if kind == "single" else (3.0, 1.25)
    return {
        "value_m3_wh": value,
        "grade": "节能级"
        if value >= saving
        else ("合格级" if value >= qualified else "未达到合格级"),
        "saving_limit": saving,
        "qualified_limit": qualified,
    }
