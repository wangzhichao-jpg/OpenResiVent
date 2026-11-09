"""理想湿空气计算；参考 ASHRAE Fundamentals 2017 第 1 章式 5–7、20、30、32。

饱和蒸汽压采用 Hyland–Wexler 拟合；焓以 0 ℃ 干空气和液态水为基准。
"""

import math

from scipy.optimize import brentq

R_DRY = 287.055  # J/(kg·K)，ASHRAE Fundamentals 2017 第 1 章
EPSILON = 0.621945  # 水蒸气与干空气摩尔质量比，同上


def pressure_at_altitude(altitude: float) -> float:
    """标准大气压力：海拔 altitude（m）→ 压力（Pa）；ASHRAE 2017 第 1 章式 3。"""
    if not -500 <= altitude <= 11000:
        raise ValueError("标准大气模型仅支持 -500 至 11000 m")
    return 101325 * (1 - 2.25577e-5 * altitude) ** 5.2559


def saturation_pressure(temperature: float) -> float:
    """饱和水汽压：温度 temperature（K）→ 压力（Pa）；Hyland–Wexler。"""
    t = temperature
    if not 173.15 <= t <= 473.15:
        raise ValueError("温度超出 Hyland–Wexler 适用范围")
    if t <= 273.15:
        logp = (
            -5.6745359e3 / t
            + 6.3925247
            - 9.677843e-3 * t
            + 6.2215701e-7 * t**2
            + 2.0747825e-9 * t**3
            - 9.484024e-13 * t**4
            + 4.1635019 * math.log(t)
        )
    else:
        logp = (
            -5.8002206e3 / t
            + 1.3914993
            - 4.8640239e-2 * t
            + 4.1764768e-5 * t**2
            - 1.4452093e-8 * t**3
            + 6.5459673 * math.log(t)
        )
    return math.exp(logp)


def humidity_ratio(temperature: float, relative_humidity: float, pressure: float) -> float:
    """温度（K）、相对湿度（0–1）、总压（Pa）→ 含湿量（kg/kg 干空气）。"""
    if not 0 <= relative_humidity <= 1 or pressure <= 0:
        raise ValueError("相对湿度或总压力无效")
    vapor = relative_humidity * saturation_pressure(temperature)
    if vapor >= pressure:
        raise ValueError("水汽分压必须低于总压力")
    return EPSILON * vapor / (pressure - vapor)


def relative_humidity(temperature: float, ratio: float, pressure: float) -> float:
    """温度（K）、含湿量（kg/kg）、总压（Pa）→ 相对湿度（0–1）。"""
    if ratio < 0 or pressure <= 0:
        raise ValueError("含湿量或压力无效")
    rh = pressure * ratio / (EPSILON + ratio) / saturation_pressure(temperature)
    if rh > 1 + 1e-10:
        raise ValueError("输入为空气过饱和状态")
    return min(rh, 1.0)


def dew_point(temperature: float, relative_humidity_value: float) -> float:
    """温度（K）、相对湿度（0–1）→ 露点（K），零湿度无有限露点。"""
    if not 0 < relative_humidity_value <= 1:
        raise ValueError("露点要求相对湿度大于零且不大于一")
    vapor = relative_humidity_value * saturation_pressure(temperature)
    if vapor < saturation_pressure(173.15):
        raise ValueError("露点低于公式适用温度")
    return brentq(lambda t: saturation_pressure(t) - vapor, 173.15, temperature)


def enthalpy(temperature: float, ratio: float) -> float:
    """温度（K）、含湿量（kg/kg）→ 比焓（J/kg 干空气）。"""
    if ratio < 0:
        raise ValueError("含湿量不能为负")
    t = temperature - 273.15
    return 1000 * (1.006 * t + ratio * (2501 + 1.86 * t))


def density(temperature: float, pressure: float, ratio: float = 0) -> float:
    """温度（K）、压力（Pa）、含湿量（kg/kg）→ 湿空气密度（kg/m³）。"""
    if temperature <= 0 or pressure <= 0 or ratio < 0:
        raise ValueError("温度、压力或含湿量无效")
    return pressure * (1 + ratio) / (R_DRY * temperature * (1 + ratio / EPSILON))


def ppm_to_mg_m3(ppm: float, molar_mass: float, temperature: float, pressure: float) -> float:
    """体积浓度 ppm、摩尔质量 kg/mol、温度 K、压力 Pa → 质量浓度 mg/m³。

    理想气体状态方程；通用气体常数取 CODATA 2018 定义值 8.314462618 J/(mol·K)。
    """
    if min(ppm, molar_mass) < 0 or temperature <= 0 or pressure <= 0:
        raise ValueError("输入不合法")
    return ppm * pressure * molar_mass / (8.314462618 * temperature)


def mg_m3_to_ppm(value: float, molar_mass: float, temperature: float, pressure: float) -> float:
    """质量浓度 mg/m³、摩尔质量 kg/mol、温度 K、压力 Pa → 体积浓度 ppm。"""
    if molar_mass <= 0:
        raise ValueError("摩尔质量必须为正")
    return value / ppm_to_mg_m3(1, molar_mass, temperature, pressure)
