"""稳态多区域压力网络：书稿式 3-6 至 3-8；单位采用 SI。"""

from dataclasses import dataclass
from math import copysign, sqrt

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

from openresivent.core.psychrometrics import density

G = 9.81  # m/s²；示例条件 A10 第一组常数


@dataclass(frozen=True)
class Zone:
    """节点温度 K、压力 Pa、参考高度 m、体积 m³；fixed 表示边界压力。"""

    temperature: float
    pressure: float = 0.0
    elevation: float = 0.0
    volume: float = 1.0
    fixed: bool = False
    density_kg_m3: float | None = None


@dataclass(frozen=True)
class Link:
    """节点间连接：height m，power 为 n，coefficient 为 m³/(s·Paⁿ)。"""

    start: str
    end: str
    coefficient: float
    power: float
    height: float = 0.0
    wind_pressure: float = 0.0
    element: object | None = None
    reference_density: float | None = None
    reference_temperature: float | None = None


def orifice_coefficient(discharge: float, area: float, rho: float) -> float:
    """流量系数、面积 m²、密度 kg/m³ → 孔口系数 m³/(s·Pa⁰·⁵)。"""
    if discharge <= 0 or area <= 0 or rho <= 0:
        raise ValueError("孔口参数必须为正")
    return discharge * area * sqrt(2 / rho)


def wind_pressure(cp: float, rho: float, speed: float) -> float:
    """风压系数、密度 kg/m³、风速 m/s → 风压 Pa；书稿式 3-1。"""
    if rho <= 0 or speed < 0:
        raise ValueError("密度和风速无效")
    return cp * rho * speed**2 / 2


def flow_and_derivative(
    dp: float, coefficient: float, power: float, epsilon: float = 1e-5
) -> tuple[float, float]:
    """压差 Pa、系数及指数 → 体积流量 m³/s 与梯度 m³/(s·Pa)。"""
    if coefficient <= 0 or not 0 < power <= 1 or epsilon <= 0:
        raise ValueError("流动元件参数无效")
    if abs(dp) < epsilon:
        derivative = coefficient * epsilon ** (power - 1)
        return derivative * dp, derivative
    return copysign(coefficient * abs(dp) ** power, dp), coefficient * power * abs(dp) ** (
        power - 1
    )


def solve(
    zones: dict[str, Zone],
    links: list[Link],
    *,
    pressure_absolute: float = 101325,
    tolerance: float = 1e-8,
    max_iterations: int = 100,
    verify_jacobian: bool = False,
) -> dict:
    """求稳态网络；节点压差 Pa，按上游密度换算质量流量 kg/s。"""
    if not zones or not any(z.fixed for z in zones.values()):
        raise ValueError("至少需要一个定压节点")
    if any(z.temperature <= 0 or z.volume <= 0 for z in zones.values()):
        raise ValueError("节点温度和容积必须为正")
    names = [name for name, z in zones.items() if not z.fixed]
    index = {name: i for i, name in enumerate(names)}
    pressures = np.array([zones[name].pressure for name in names], dtype=float)
    if any(z.density_kg_m3 is not None and z.density_kg_m3 <= 0 for z in zones.values()):
        raise ValueError("指定密度必须为正")
    densities = {
        name: (
            z.density_kg_m3
            if z.density_kg_m3 is not None
            else density(z.temperature, pressure_absolute)
        )
        for name, z in zones.items()
    }
    if any(
        link.start not in zones or link.end not in zones or link.start == link.end for link in links
    ):
        raise ValueError("连接端点无效")
    reachable = {name for name, zone in zones.items() if zone.fixed}
    while True:
        previous = len(reachable)
        for link in links:
            if link.start in reachable or link.end in reachable:
                reachable.update((link.start, link.end))
        if len(reachable) == previous:
            break
    if len(reachable) != len(zones):
        raise ValueError("网络中存在未连接定压节点的区域")

    def residual(p, jacobian=False):
        values = {
            name: (p[index[name]] if name in index else z.pressure) for name, z in zones.items()
        }
        residuals = np.zeros(len(names))
        matrix = lil_matrix((len(names), len(names)), dtype=float)
        flows = []
        for link in links:
            za, zb = zones[link.start], zones[link.end]
            dp = (
                values[link.start]
                - densities[link.start] * G * (link.height - za.elevation)
                - values[link.end]
                + densities[link.end] * G * (link.height - zb.elevation)
                + link.wind_pressure
            )
            q, derivative = (
                link.element.flow(dp)
                if link.element is not None
                else flow_and_derivative(dp, link.coefficient, link.power)
            )
            upstream = link.start if q >= 0 else link.end
            rho = densities[upstream]
            # TN 1887r1 p.265 式(24)的体积系数形式。未指定时以起点状态为参考。
            from openresivent.network.elements import CheckValve, Orifice, PowerLaw

            if link.element is None or isinstance(link.element, (PowerLaw, CheckValve, Orifice)):
                n = (
                    link.element.exponent
                    if isinstance(link.element, PowerLaw)
                    else (
                        link.element.exponent
                        if isinstance(link.element, CheckValve) and dp < 0
                        else (
                            0.5 if isinstance(link.element, (CheckValve, Orifice)) else link.power
                        )
                    )
                )
                rho0 = (
                    link.reference_density
                    if link.reference_density is not None
                    else densities[link.start]
                )
                if isinstance(link.element, Orifice):
                    rho0 = link.element.reference_density
                t0 = (
                    link.reference_temperature
                    if link.reference_temperature is not None
                    else za.temperature
                )
                if rho0 <= 0 or t0 <= 0:
                    raise ValueError("参考状态必须为正")
                mu0 = 3.7143e-6 + 4.9286e-8 * t0
                mu = 3.7143e-6 + 4.9286e-8 * zones[upstream].temperature
                factor = (rho0 / rho) ** n * ((mu0 / rho0) / (mu / rho)) ** (2 * n - 1)
                q *= factor
                derivative *= factor
            mass = q * rho
            flows.append({"volume_flow": q, "mass_flow": mass, "delta_p": dp})
            for node, sign in ((link.start, 1), (link.end, -1)):
                if node in index:
                    i = index[node]
                    residuals[i] += sign * mass
                    for other, direction in ((link.start, 1), (link.end, -1)):
                        if other in index:
                            matrix[i, index[other]] += sign * direction * rho * derivative
        return residuals, matrix, flows

    for iteration in range(max_iterations + 1):
        r, matrix, flows = residual(pressures)
        if verify_jacobian and len(pressures):
            finite = np.zeros((len(names), len(names)))
            for col in range(len(names)):
                h = 1e-7 * max(1.0, abs(pressures[col]))
                delta = np.zeros(len(names))
                delta[col] = h
                finite[:, col] = (
                    residual(pressures + delta)[0] - residual(pressures - delta)[0]
                ) / (2 * h)
            analytic = matrix.toarray()
            scale = max(float(np.max(np.abs(finite))), 1e-15)
            if np.max(np.abs(analytic - finite)) / scale > 1e-5:
                raise ValueError("解析雅可比与中心差分不一致；检查元件拐点、零流及密度切换")
        error = float(np.max(np.abs(r))) if len(r) else 0.0
        if error < tolerance:
            return {
                "pressures": {name: float(pressures[i]) for name, i in index.items()},
                "flows": flows,
                "mass_residual": error,
                "iterations": iteration,
            }
        step = spsolve(matrix.tocsr(), -r)
        if not np.all(np.isfinite(step)):
            raise ValueError("网络奇异或未连接定压节点")
        scale = 1.0
        while scale > 1e-6:
            candidate = pressures + scale * step
            if np.linalg.norm(residual(candidate)[0]) < np.linalg.norm(r):
                pressures = candidate
                break
            scale /= 2
        else:
            largest = int(np.argmax(np.abs(r)))
            connected = [
                f"{j}:{x.start}→{x.end}"
                for j, x in enumerate(links)
                if names[largest] in (x.start, x.end)
            ]
            raise RuntimeError(
                f"网络线搜索未收敛；最大残差节点 {names[largest]}={r[largest]:.6g} kg/s；相关元件 {connected}"
            )
    largest = int(np.argmax(np.abs(r)))
    connected = [
        f"{j}:{x.start}→{x.end}" for j, x in enumerate(links) if names[largest] in (x.start, x.end)
    ]
    raise RuntimeError(
        f"网络迭代未收敛；最大残差节点 {names[largest]}={r[largest]:.6g} kg/s；相关元件 {connected}"
    )
