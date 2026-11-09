"""M2 流动元件，均以 Pa、m³/s、kg/m³、m 为单位。

幂律与孔口依据书稿式 3-7、3-8；管道按 Darcy–Weisbach 和
Colebrook（默认）或 Swamee–Jain；止回阀漏风依据书稿 5.4.1、式 5-8。风机和调节阀
的工作边界与外推为下述显式模型，不代表真实产品曲线。
"""

from dataclasses import dataclass
from math import copysign, log, log10, pi, sqrt

import numpy as np
from scipy.optimize import brentq

from openresivent.network.solver import flow_and_derivative


def airtightness_coefficient(n50: float, volume: float, exponent: float = 0.65) -> float:
    """n50 s⁻¹、体积 m³、幂指数 → C（m³/(s·Paⁿ)）。"""
    if n50 <= 0 or volume <= 0 or not 0 < exponent <= 1:
        raise ValueError("气密性参数无效")
    return n50 * volume / 50**exponent


def leakage_coefficient(flow_50: float, exponent: float = 0.65) -> float:
    """50 Pa 总泄漏风量 N₅₀（m³/s）及指数 → C（m³/(s·Paⁿ)）。"""
    if flow_50 <= 0 or not 0 < exponent <= 1:
        raise ValueError("50 Pa 风量或指数无效")
    return flow_50 / 50**exponent


@dataclass(frozen=True)
class PowerLaw:
    """幂律缝隙：C 为 m³/(s·Paⁿ)，指数无量纲。"""

    coefficient: float
    exponent: float = 0.65

    def flow(self, dp: float) -> tuple[float, float]:
        """压差 Pa → 风量 m³/s 与压差导数 m³/(s·Pa)。"""
        return flow_and_derivative(dp, self.coefficient, self.exponent)


@dataclass(frozen=True)
class Orifice:
    """锐边孔口，流量系数无量纲、面积 m²；参考 293.15 K、101325 Pa。"""

    discharge: float
    area: float
    reference_density: float = 101325 / (287.055 * 293.15)

    def flow(self, dp: float) -> tuple[float, float]:
        """参考密度下压差 Pa → 体积流量 m³/s 及导数。"""
        if min(self.discharge, self.area, self.reference_density) <= 0:
            raise ValueError("孔口参数必须为正")
        return flow_and_derivative(
            dp, self.discharge * self.area * sqrt(2 / self.reference_density), 0.5
        )


@dataclass(frozen=True)
class ConstantFlow:
    """理想定风量，flow_rate m³/s，正值为起点到终点。"""

    flow_rate: float

    def flow(self, dp: float) -> tuple[float, float]:
        """压差 Pa → 固定风量 m³/s 和零导数。"""
        return self.flow_rate, 0.0


@dataclass(frozen=True)
class CheckValve:
    """正向开启压差 Pa、正向孔口系数、250 Pa 反向漏风量 m³/s。"""

    opening_pressure: float
    forward_coefficient: float
    leakage_250: float
    exponent: float = 0.65

    @classmethod
    def from_area_rating(
        cls,
        opening_pressure: float,
        forward_coefficient: float,
        leakage_per_area: float,
        area: float,
        exponent: float = 0.65,
    ):
        """250 Pa 单位面积漏风 m³/(s·m²)、面积 m² → 止回阀。"""
        if leakage_per_area <= 0 or area <= 0:
            raise ValueError("漏风量和面积必须为正")
        return cls(opening_pressure, forward_coefficient, leakage_per_area * area, exponent)

    def flow(self, dp: float) -> tuple[float, float]:
        """压差 Pa → 风量 m³/s 和导数；滞回及阀片动态不建模。"""
        if self.opening_pressure < 0 or self.forward_coefficient <= 0 or self.leakage_250 <= 0:
            raise ValueError("止回阀参数无效")
        if dp < 0:
            return flow_and_derivative(dp, self.leakage_250 / 250**self.exponent, self.exponent)
        if dp <= self.opening_pressure:
            return 0.0, 0.0
        return flow_and_derivative(dp - self.opening_pressure, self.forward_coefficient, 0.5)


@dataclass(frozen=True)
class ConstantVolumeValve:
    """稳态恒风量阀：设定 m³/s，工作区间下、上界 Pa。

    两端孔口系数各自取使其在工作边界等于设定风量；反向沿用下限孔口。
    本模型为静态包络，不模拟 PID 动态和执行器。
    """

    setpoint: float
    lower: float
    upper: float

    def flow(self, dp: float) -> tuple[float, float]:
        """压差 Pa → 风量 m³/s 与导数。"""
        if self.setpoint <= 0 or not 0 < self.lower < self.upper:
            raise ValueError("恒风量阀参数无效")
        if dp < self.lower:
            return flow_and_derivative(dp, self.setpoint / sqrt(self.lower), 0.5)
        if dp <= self.upper:
            return self.setpoint, 0.0
        return flow_and_derivative(dp, self.setpoint / sqrt(self.upper), 0.5)


@dataclass(frozen=True)
class PolynomialFan:
    """多项式压升 p(q)=Σ aᵢqⁱ，q 为 m³/s，定义域 [0,q_max]。

    仅接受严格下降曲线；边界外使用端点切线延拓，端点斜率为零时
    使用全曲线割线斜率，从而明确定义倒流及超过标定范围的流量。
    """

    coefficients: tuple[float, ...]
    q_max: float

    def flow(self, dp: float) -> tuple[float, float]:
        """压差 Pa（起点减终点）→ 有符号风量 m³/s 及导数。"""
        if self.q_max <= 0 or len(self.coefficients) < 2:
            raise ValueError("风机曲线参数无效")
        coeff = np.array(self.coefficients, dtype=float)
        dcoeff = np.polynomial.polynomial.polyder(coeff)
        p = lambda q: float(np.polynomial.polynomial.polyval(q, coeff))
        slope = lambda q: float(np.polynomial.polynomial.polyval(q, dcoeff))
        critical = (
            np.polynomial.polynomial.polyroots(np.polynomial.polynomial.polyder(dcoeff))
            if len(dcoeff) > 1
            else []
        )
        points = [0.0, self.q_max] + [
            float(x.real) for x in critical if abs(x.imag) < 1e-10 and 0 < x.real < self.q_max
        ]
        if p(0) <= p(self.q_max) or any(slope(q) > 1e-10 for q in points):
            raise ValueError("风机曲线必须单调下降")
        secant = (p(self.q_max) - p(0)) / self.q_max
        gain = -dp
        if gain >= p(0):
            s = min(slope(0), secant * 1e-6)
            return (gain - p(0)) / s, -1 / s
        if gain <= p(self.q_max):
            s = min(slope(self.q_max), secant * 1e-6)
            return self.q_max + (gain - p(self.q_max)) / s, -1 / s
        q = brentq(lambda x: p(x) - gain, 0, self.q_max, xtol=1e-14)
        s = slope(q)
        if s >= 0:
            raise ValueError("风机曲线局部斜率为零，无法求导")
        return q, -1 / s


@dataclass(frozen=True)
class LaminarDuct:
    """圆管层流 Darcy 与局部阻力，均为 SI；超出层流范围明确报错。"""

    length: float
    diameter: float
    local_loss: float
    rho: float = 1.2
    viscosity: float = 1.81e-5

    def flow(self, dp: float) -> tuple[float, float]:
        """压差 Pa → 风量 m³/s 与导数；要求 Re < 2300。"""
        if min(self.length, self.diameter, self.rho, self.viscosity) <= 0 or self.local_loss < 0:
            raise ValueError("风管参数无效")
        area = pi * self.diameter**2 / 4
        a = 32 * self.viscosity * self.length / (self.diameter**2 * area)
        b = self.local_loss * self.rho / (2 * area**2)
        q = 2 * abs(dp) / (a + sqrt(a * a + 4 * b * abs(dp)))
        if self.rho * q * self.diameter / (self.viscosity * area) >= 2300:
            raise ValueError("层流风管 Re 超出适用范围")
        return copysign(q, dp), 1 / (a + 2 * b * q)


@dataclass(frozen=True)
class Duct:
    """圆形风管：长度、直径、粗糙度 m，局阻系数，无量纲；空气密度及动力黏度。"""

    length: float
    diameter: float
    roughness: float
    local_loss: float
    rho: float = 1.2
    viscosity: float = 1.81e-5
    method: str = "colebrook"

    def _pressure(self, q: float) -> tuple[float, float]:
        """正向 q m³/s → 阻力 Pa 和导数 Pa/(m³/s)。"""
        area = pi * self.diameter**2 / 4
        k = self.rho * self.diameter / (self.viscosity * area)
        re = k * q
        lam = 32 * self.viscosity * self.length / (self.diameter**2 * area)
        local = self.local_loss * self.rho / (2 * area**2)
        if re < 2300:
            return lam * q + local * q * q, lam + 2 * local * q
        if self.method == "colebrook":
            # M6 是同一 Colebrook 关联式；过渡区沿用 M6 的线性插值。
            from openresivent.duct.hydraulics import friction_factor

            f = friction_factor(re, self.roughness / self.diameter)
            step = re * 1e-5
            df_dq = (
                (
                    friction_factor(re + step, self.roughness / self.diameter)
                    - friction_factor(re - step, self.roughness / self.diameter)
                )
                / (2 * step)
                * k
            )
            factor = self.rho / (2 * area**2)
            resistance = factor * (f * self.length / self.diameter + self.local_loss)
            return (
                resistance * q * q,
                2 * resistance * q + factor * self.length / self.diameter * df_dq * q * q,
            )
        a = self.roughness / (3.7 * self.diameter) + 5.74 / re**0.9
        l = log10(a)
        f = 0.25 / l**2
        df_dq = -0.5 / l**3 * (-0.9 * 5.74 / re**1.9 * k) / (a * log(10))
        factor = self.rho / (2 * area**2)
        resistance = factor * (f * self.length / self.diameter + self.local_loss)
        turbulent = resistance * q * q
        derivative = 2 * resistance * q + factor * self.length / self.diameter * df_dq * q * q
        if re >= 4000:
            return turbulent, derivative
        weight = (re - 2300) / 1700
        low = lam * q + local * q * q
        low_derivative = lam + 2 * local * q
        return (1 - weight) * low + weight * turbulent, (
            1 - weight
        ) * low_derivative + weight * derivative + k / 1700 * (turbulent - low)

    def flow(self, dp: float) -> tuple[float, float]:
        """压差 Pa → 风量 m³/s 和导数；过渡区可能不连续，见理论手册。"""
        if (
            self.length <= 0
            or self.diameter <= 0
            or self.roughness < 0
            or self.local_loss < 0
            or self.rho <= 0
            or self.viscosity <= 0
            or self.method not in ("colebrook", "swamee-jain")
        ):
            raise ValueError("管道参数无效")
        area = pi * self.diameter**2 / 4
        laminar_k = 32 * self.viscosity * self.length / (self.diameter**2 * area)
        if abs(dp) < 1e-12:
            return dp / laminar_k, 1 / laminar_k
        high = area
        while self._pressure(high)[0] < abs(dp):
            high *= 2
        q = brentq(lambda x: self._pressure(x)[0] - abs(dp), 0, high, xtol=1e-14)
        return copysign(q, dp), 1 / self._pressure(q)[1]
