"""厨房补风反算：基于既有等温多区网络，不改变正算边界。"""

from scipy.optimize import brentq

from openresivent.dwelling.templates import Dwelling, calculate


def minimum_makeup(home: Dwelling, *, mode: str, threshold_pa: float = 15.0, **conditions) -> dict:
    """反算厨房本地最小补风；机械值 m³/s，自然开口面积 m²。

    其他设备条件传给 calculate；两种方案分别求解，不能同时叠加另一种补风。
    阈值是示例提示值，不是燃气安全限值。零补风已满足时返回零，
    给定搜索上限仍无法满足时明确抛出异常，不伪造解。
    """
    if mode not in ("mechanical", "opening") or threshold_pa <= 0:
        raise ValueError("补风方式或阈值无效")
    if "opening_area" in conditions or "mechanical_makeup" in conditions:
        raise ValueError("反算不接受已叠加的补风设备")
    field = "mechanical_makeup" if mode == "mechanical" else "opening_area"
    room = "makeup_room" if mode == "mechanical" else "opening_room"
    conditions = dict(conditions)
    conditions[room] = "kitchen"

    def residual(x):
        outcome = calculate(home, threshold_pa=threshold_pa, **conditions, **{field: x})
        return outcome["pressures_pa"][outcome["gas_zone"]] + threshold_pa

    initial = residual(0.0)
    if initial >= 0:
        return {
            "value": 0.0,
            "pressure_pa": initial - threshold_pa,
            "already_satisfied": True,
            "tolerance_pa": 0.01,
        }
    upper = 0.01 if mode == "mechanical" else 0.001
    bound = 10.0 if mode == "mechanical" else 100.0
    while upper < bound and residual(upper) < 0:
        upper = min(upper * 2, bound)
    if residual(upper) < 0:
        raise ValueError("搜索上限内无法满足负压提示阈值")
    root = brentq(residual, 0.0, upper, xtol=1e-11, rtol=1e-12, maxiter=100)
    pressure = residual(root) - threshold_pa
    if abs(pressure + threshold_pa) > 0.01:
        raise ValueError("反算压力残差超过 0.01 Pa")
    return {
        "value": root,
        "pressure_pa": pressure,
        "already_satisfied": False,
        "tolerance_pa": 0.01,
    }
