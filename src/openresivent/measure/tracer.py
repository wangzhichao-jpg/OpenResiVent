"""示踪气体浓度衰减；书稿 6.2 式 6-11 至 6-17。"""

import csv
import math
from pathlib import Path

import numpy as np
from scipy.stats import linregress, t


def two_point(c0: float, c1: float, background: float, elapsed: float) -> float:
    """两点浓度及背景同单位、间隔 elapsed（s）→ 换气次数（s⁻¹）。"""
    if elapsed <= 0 or min(c0 - background, c1 - background) <= 0:
        raise ValueError("时间须为正，浓度须高于背景")
    return math.log((c0 - background) / (c1 - background)) / elapsed


def decay(times: list[float], concentrations: list[float], background: float) -> dict:
    """时间序列 s、同单位浓度及背景 → 衰减率 s⁻¹、95% 区间及空气龄 s。"""
    x = np.asarray(times, dtype=float)
    c = np.asarray(concentrations, dtype=float) - background
    if (
        len(x) < 3
        or len(x) != len(c)
        or not np.all(np.isfinite(x))
        or not np.all(np.isfinite(c))
        or np.any(c <= 0)
        or np.any(np.diff(x) <= 0)
    ):
        raise ValueError("至少三个有序时间点，浓度须高于背景")
    fit = linregress(x, np.log(c))
    rate = -fit.slope
    if rate <= 0:
        raise ValueError("尾部外推要求衰减率为正")
    bound = t.ppf(0.975, len(x) - 2) * fit.stderr
    age = (np.trapezoid(c, x) + c[-1] / rate) / c[0]
    return {
        "rate": rate,
        "ci95": [rate - bound, rate + bound],
        "local_age": age,
        "r_squared": fit.rvalue**2,
    }


def local_mean_air_age(
    times: list[float],
    concentrations: list[float],
    background: float = 0,
    tail_rate: float | None = None,
) -> float:
    """采样时间 s、浓度及背景（同单位）、尾部指数衰减率 s⁻¹ → 局部空气龄 s。

    浓度已归零时可不外推；末值仍高于背景时必须明确指定正尾部衰减率。
    积分依据书稿式 6-17；不能依赖尚未衰减的数据假定尾部为零。
    """
    x = np.asarray(times, dtype=float)
    c = np.asarray(concentrations, dtype=float) - background
    if (
        len(x) < 2
        or len(x) != len(c)
        or not np.all(np.isfinite(x))
        or not np.all(np.isfinite(c))
        or np.any(np.diff(x) <= 0)
        or abs(x[0]) > 1e-12
        or np.any(c < 0)
        or c[0] <= 0
    ):
        raise ValueError("时间或扣背景浓度无效")
    if tail_rate is not None and tail_rate <= 0:
        raise ValueError("尾部衰减率必须为正")
    if c[-1] > 0 and tail_rate is None:
        raise ValueError("浓度尚未归零，需要尾部衰减率")
    tail = c[-1] / tail_rate if tail_rate is not None else 0
    return float((np.trapezoid(c, x) + tail) / c[0])


def read_csv(path: Path) -> dict[str, list[float]]:
    """读取首列 time_s、其余列浓度的 CSV；返回列名到数值的字典。"""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or reader.fieldnames[0] != "time_s" or len(reader.fieldnames) < 2:
            raise ValueError("首列必须为 time_s，且至少有一列浓度")
        columns = {name: [] for name in reader.fieldnames}
        for row in reader:
            for name, values in columns.items():
                values.append(float(row[name]))
    return columns
