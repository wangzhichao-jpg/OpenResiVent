"""二次风机曲线解析基准，依据开发方案第 8.2 节 B05。"""

import math


def quadratic_fan_flow(free_flow: float, shutoff_pressure: float, back_pressure: float) -> float:
    """自由风量 m³/s、零流量静压 Pa、外部背压 Pa → 工作风量 m³/s。

    假设风机曲线为 Δp=Δp₀[1-(Q/Q₀)²]，且工作压差非负、不超过最大静压；
    只用于 B05 解析验证，不描述反转、失速或系统交点搜索。
    """
    if free_flow <= 0 or shutoff_pressure <= 0 or not 0 <= back_pressure <= shutoff_pressure:
        raise ValueError("风机基准参数或背压无效")
    return free_flow * math.sqrt(1 - back_pressure / shutoff_pressure)
