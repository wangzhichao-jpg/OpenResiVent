"""单区完全混合的污染物稳态与瞬态稀释，依据书稿式 2-3、2-16 至 2-18。"""

import math


def steady_flow(generation: float, outdoor: float, limit: float) -> float:
    """产生率 kg/s、浓度 kg/m³ → 所需风量 m³/s。"""
    if generation < 0 or outdoor < 0 or limit <= outdoor:
        raise ValueError("排放量或浓度无效")
    return generation / (limit - outdoor)


def concentration(
    initial: float, outdoor: float, generation: float, flow: float, volume: float, elapsed: float
) -> float:
    """浓度 kg/m³、源强 kg/s、风量 m³/s、体积 m³、时间 s → 浓度 kg/m³。"""
    if min(initial, outdoor, generation, elapsed) < 0 or flow <= 0 or volume <= 0:
        raise ValueError("输入无效")
    steady = outdoor + generation / flow
    return steady + (initial - steady) * math.exp(-flow * elapsed / volume)


def time_to_target(initial: float, steady: float, target: float, rate: float) -> float:
    """初值、稳态和目标浓度同为 kg/m³，换气率 s⁻¹ → 达标时间 s。"""
    if rate <= 0 or min(initial, steady, target) < 0:
        raise ValueError("输入无效")
    if initial == target:
        return 0.0
    if initial == steady:
        raise ValueError("恒定浓度不能到达该目标")
    ratio = (target - steady) / (initial - steady)
    if not 0 < ratio <= 1:
        raise ValueError("目标不可在有限非负时间内达到")
    return -math.log(ratio) / rate


def time_to_95_percent(rate: float) -> float:
    """换气率 s⁻¹ → 初始偏差衰减 95% 所需时间 s。"""
    if rate <= 0:
        raise ValueError("换气率必须为正")
    return math.log(20) / rate
