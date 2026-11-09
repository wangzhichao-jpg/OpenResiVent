"""多区充分混合污染物传输，线性常系数区间采用矩阵指数精确积分。

质量平衡见书稿 6.6.1；浓度 kg/m³、体积 m³、风量 m³/s、源 kg/s、
沉降率 s⁻¹。空气流量视为给定且稳态守恒，过滤效率定义为路径去除比例。
"""

import itertools
from dataclasses import dataclass

import numpy as np
from scipy.linalg import expm


@dataclass(frozen=True)
class TransportPath:
    """定向空气路径：室外以 None 表示；流量 m³/s，过滤效率 0–1。"""

    start: int | None
    end: int | None
    flow: float
    efficiency: float = 0.0


def transport_matrix(volumes, paths, deposition, outdoor_concentration=0.0):
    """区域体积 m³、路径、沉降率 s⁻¹、室外浓度 kg/m³ → A、b。"""
    v = np.asarray(volumes, dtype=float)
    d = np.asarray(deposition, dtype=float)
    if (
        v.ndim != 1
        or not len(v)
        or d.shape != v.shape
        or np.any(v <= 0)
        or np.any(d < 0)
        or outdoor_concentration < 0
    ):
        raise ValueError("区域和沉降参数无效")
    n = len(v)
    a = np.diag(-d)
    b = np.zeros(n)
    for path in paths:
        if (
            path.start == path.end
            or path.flow < 0
            or not 0 <= path.efficiency <= 1
            or any(i is not None and not 0 <= i < n for i in (path.start, path.end))
        ):
            raise ValueError("污染物路径无效")
        if path.start is not None:
            a[path.start, path.start] -= path.flow / v[path.start]
        if path.end is not None:
            inflow = path.flow * (1 - path.efficiency) / v[path.end]
            if path.start is None:
                b[path.end] += inflow * outdoor_concentration
            else:
                a[path.end, path.start] += inflow
    return a, b


def integrate(volumes, paths, deposition, initial, times, schedule, outdoor_concentration=0.0):
    """时间 s、分段常数源 [(开始时间 s, 各区 kg/s), …] → 浓度数组 kg/m³。

    跨越源项切换时自动拆步；矩阵指数对分段常系数精确，支持奇异矩阵。
    """
    v = np.asarray(volumes, dtype=float)
    current = np.asarray(initial, dtype=float)
    t = np.asarray(times, dtype=float)
    if (
        current.shape != v.shape
        or np.any(current < 0)
        or t.ndim != 1
        or len(t) < 1
        or np.any(np.diff(t) <= 0)
        or not schedule
    ):
        raise ValueError("初值、时间或源项无效")
    schedule = sorted(
        ((float(start), np.asarray(src, dtype=float)) for start, src in schedule),
        key=lambda item: item[0],
    )
    if (
        schedule[0][0] > t[0]
        or any(s.shape != v.shape or np.any(s < 0) for _, s in schedule)
        or any(schedule[i][0] == schedule[i - 1][0] for i in range(1, len(schedule)))
    ):
        raise ValueError("源项时间表无效")
    a, b = transport_matrix(v, paths, deposition, outdoor_concentration)
    result = [current.copy()]
    n = len(v)
    for left, right in itertools.pairwise(t):
        boundaries = [left] + [s for s, _ in schedule if left < s < right] + [right]
        for start, end in itertools.pairwise(boundaries):
            source = next(src for when, src in reversed(schedule) if when <= start)
            augmented = np.zeros((n + 1, n + 1))
            augmented[:n, :n] = a
            augmented[:n, n] = b + source / v
            current = (expm(augmented * (end - start)) @ np.r_[current, 1])[:n]
        result.append(current.copy())
    return np.array(result)
