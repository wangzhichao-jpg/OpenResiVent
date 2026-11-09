"""风管水力：Darcy–Weisbach，书稿 4.1.3 式 4.4–4.5。

输入统一 SI；矩形风管按水力直径 4A/P。局部阻力系数由调用者提供。
"""

from dataclasses import dataclass, replace
from math import log10, pi

import numpy as np
from scipy.optimize import brentq, least_squares

from openresivent.core.psychrometrics import density
from openresivent.network.elements import PolynomialFan


def friction_factor(reynolds: float, relative_roughness: float, method: str = "colebrook") -> float:
    """雷诺数、相对粗糙度（无量纲）→ Darcy 摩擦系数（无量纲）。"""
    if reynolds <= 0 or not 0 <= relative_roughness < 1:
        raise ValueError("雷诺数或粗糙度无效")
    if method not in ("colebrook", "altshul"):
        raise ValueError("未知摩擦关联式")
    if reynolds < 2300:
        return 64 / reynolds
    if reynolds < 4000:
        # 过渡区仅作连续插值，工程应用需结合不确定性复核。
        fraction = (reynolds - 2300) / 1700
        return (1 - fraction) * 64 / reynolds + fraction * friction_factor(
            4000, relative_roughness, method
        )
    if method == "altshul":
        return 0.11 * (relative_roughness + 68 / reynolds) ** 0.25
    return brentq(
        lambda f: 1 / f**0.5 + 2 * log10(relative_roughness / 3.7 + 2.51 / (reynolds * f**0.5)),
        0.005,
        0.2,
    )


@dataclass(frozen=True)
class DuctSegment:
    """风管长度 m、风量 m³/s、粗糙度 m；圆管直径或矩形宽高 m。"""

    name: str
    length: float
    flow: float
    roughness: float
    diameter: float | None = None
    width: float | None = None
    height: float | None = None
    local_zeta: float = 0.0
    role: str = "branch"

    def calculate(self, rho: float, nu: float, method: str = "colebrook") -> dict:
        """密度 kg/m³、运动黏度 m²/s → 管段风速、雷诺数、损失及条文检查。"""
        if min(self.length, self.flow, rho, nu) <= 0 or self.roughness < 0 or self.local_zeta < 0:
            raise ValueError("风管数据无效")
        if self.diameter is not None and self.width is None and self.height is None:
            if self.diameter <= 0:
                raise ValueError("直径须大于零")
            area, dh = pi * self.diameter**2 / 4, self.diameter
        elif (
            self.diameter is None
            and self.width
            and self.height
            and min(self.width, self.height) > 0
        ):
            area = self.width * self.height
            dh = 2 * self.width * self.height / (self.width + self.height)
        else:
            raise ValueError("须给出圆管直径或矩形长宽")
        velocity = self.flow / area
        re = velocity * dh / nu
        factor = friction_factor(re, self.roughness / dh, method)
        dynamic = rho * velocity**2 / 2
        low, high = {"main": (3.5, 4.5), "branch": (2.0, 3.0)}.get(self.role, (None, None))
        if low is None:
            raise ValueError("风管角色须为 main 或 branch")
        return {
            "velocity_m_s": velocity,
            "reynolds": re,
            "friction_factor": factor,
            "dynamic_pressure_pa": dynamic,
            "friction_pa": factor * self.length / dh * dynamic,
            "local_pa": self.local_zeta * dynamic,
            "recommended_speed_passed": low <= velocity <= high,
            "maximum_speed_passed": velocity <= 6,
            "hydraulic_diameter_m": dh,
        }


def airflow_properties(temperature: float, pressure: float) -> tuple[float, float]:
    """温度 K、绝对压力 Pa → 密度 kg/m³、运动黏度 m²/s。

    密度取 M0；动力黏度使用 CONTAM TN 1887 第 258 页线性式，适用于常温空气。
    """
    if not 250 <= temperature <= 320:
        raise ValueError("黏度关联式仅用于 250–320 K")
    rho = density(temperature, pressure)
    return rho, (3.7143e-6 + 4.9286e-8 * temperature) / rho


def balance(pressure_a: float, pressure_b: float) -> dict:
    """并联支路阻力 Pa → 以较大阻力为基准的不平衡率和宜项判断。"""
    if min(pressure_a, pressure_b) < 0 or max(pressure_a, pressure_b) <= 0:
        raise ValueError("并联阻力无效")
    fraction = abs(pressure_a - pressure_b) / max(pressure_a, pressure_b)
    return {"fraction": fraction, "recommended_passed": fraction <= 0.15}


def fan_allowance(flow: float, pressure: float, *, flow_unit: str) -> dict:
    """设计风量 m³/s、设计压损 Pa → 附加区间；须显式声明 flow_unit='m3/s'。

    纯数字自身不携带单位，无法检测错误声明；工程单位应先在输入层换算。
    """
    if flow_unit != "m3/s":
        raise ValueError("内核风量仅接受 m3/s，请先换算")
    if flow <= 0 or pressure < 0:
        raise ValueError("风量或压损无效")
    return {
        "flow_m3_s": (flow * 1.05, flow * 1.10),
        "pressure_pa": (pressure * 1.10, pressure * 1.15),
    }


def fan_operating_point(
    fan: PolynomialFan,
    segments: dict[str, DuctSegment],
    route: list[str],
    rho: float,
    nu: float,
    efficiency: tuple[float, float] | None = None,
) -> dict:
    """风机、路径、密度 kg/m³、运动黏度 m²/s → 工作点 m³/s、Pa。

    各段设计风量按同一比例缩放；不对并联网络的实际流量重分配求解。
    效率参数为工作点效率和最高效率（均为无量纲，均由用户提供）。
    """
    if not route or any(n not in segments for n in route):
        raise ValueError("风机路径无效")
    design_flow = segments[route[0]].flow

    def resistance(total):
        scale = total / design_flow
        if scale <= 0:
            return 0.0
        values = [
            replace(segments[n], flow=segments[n].flow * scale).calculate(rho, nu) for n in route
        ]
        return sum(v["friction_pa"] + v["local_pa"] for v in values)

    def difference(q):
        return fan.flow(-resistance(q))[0] - q

    q = brentq(difference, fan.q_max * 0.05, fan.q_max, xtol=1e-13)
    result = {"flow_m3_s": q, "pressure_pa": resistance(q), "efficiency_passed": None}
    if efficiency is not None:
        actual, maximum = efficiency
        if not 0 <= actual <= maximum <= 1 or maximum == 0:
            raise ValueError("风机效率无效")
        result["efficiency_passed"] = actual >= 0.9 * maximum - 1e-12
    return result


def balance_parallel_flows(
    segments: dict[str, DuctSegment],
    routes: dict[str, list[str]],
    total_flow: float,
    rho: float,
    nu: float,
) -> dict:
    """并联树状网络的总风量 m³/s → 各管段/末端风量 m³/s 与环路压损 Pa。

    路径均从同一入口至同一压力出口，支持共享干管；不包含可调风阀和末端固定压差。
    用正变量求解流量守恒和各环路等压。零流、反向流及回路网络不在本模型范围。
    """
    if not segments or not routes or total_flow <= 0 or rho <= 0 or nu <= 0:
        raise ValueError("网络或总风量无效")
    names = list(routes)
    if any(
        not r or len(r) != len(set(r)) or any(s not in segments for s in r) for r in routes.values()
    ):
        raise ValueError("路径为空、重复或包含未知管段")
    # 树状路径只能有共同前缀；分叉之后不能再次汇合。
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            a, b = routes[left], routes[right]
            common = set(a) & set(b)
            prefix = []
            for x, y in zip(a, b):
                if x != y:
                    break
                prefix.append(x)
            if common != set(prefix):
                raise ValueError("路径分叉后不得重新汇合；该网络不是树状网络")
    segnames = list(segments)
    incidence = np.array(
        [[int(segment in routes[route]) for route in names] for segment in segnames]
    )
    if np.any(incidence.sum(axis=1) == 0) or len(
        {tuple(incidence[:, i]) for i in range(len(names))}
    ) != len(names):
        raise ValueError("存在未使用管段或重复路径")

    def values(terminal):
        flows = incidence @ terminal
        details = {
            name: replace(segments[name], flow=float(q)).calculate(rho, nu)
            for name, q in zip(segnames, flows, strict=True)
        }
        losses = np.array([details[s]["friction_pa"] + details[s]["local_pa"] for s in segnames])
        return flows, details, incidence.T @ losses

    def residual(q):
        _, _, p = values(q)
        return np.r_[
            (q.sum() - total_flow) / total_flow, (p[1:] - p[0]) / max(float(np.max(p)), 1e-9)
        ]

    solution = least_squares(
        residual,
        np.full(len(names), total_flow / len(names)),
        bounds=(np.full(len(names), total_flow * 1e-10), np.full(len(names), total_flow)),
        xtol=1e-12,
        ftol=1e-12,
        gtol=1e-12,
        max_nfev=2000,
    )
    if not solution.success or np.max(np.abs(residual(solution.x))) > 1e-8:
        raise RuntimeError("并联网络流量平衡未收敛")
    flows, details, pressures = values(solution.x)
    return {
        "terminal_flows_m3_s": dict(zip(names, map(float, solution.x), strict=True)),
        "segment_flows_m3_s": dict(zip(segnames, map(float, flows), strict=True)),
        "route_losses_pa": dict(zip(names, map(float, pressures), strict=True)),
        "segments": details,
        "residual": float(np.max(np.abs(residual(solution.x)))),
    }


def network(
    segments: dict[str, DuctSegment], routes: dict[str, list[str]], rho: float, nu: float
) -> dict:
    """管段和风机至末端的路径 → 分段阻力、路径阻力及最不利环路。

    不自动平衡管网流量；调用方须输入质量守恒的设计风量，路径可以共享干管。
    """
    if (
        not segments
        or not routes
        or any(not route or any(n not in segments for n in route) for route in routes.values())
    ):
        raise ValueError("路径或管段无效")
    values = {name: s.calculate(rho, nu) for name, s in segments.items()}
    losses = {
        name: sum(values[n]["friction_pa"] + values[n]["local_pa"] for n in route)
        for name, route in routes.items()
    }
    worst = max(losses, key=losses.get)
    return {
        "segments": values,
        "route_losses_pa": losses,
        "critical_route": worst,
        "pressure_pa": losses[worst],
        "imbalance": {name: balance(losses[worst], p) for name, p in losses.items()},
    }
