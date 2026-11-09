"""空气龄体积平均、流量守恒及 VTK 可选读取；不链接 OpenFOAM。"""

import re
from pathlib import Path

import numpy as np

from openresivent.measure.ventilation import air_change_efficiency


def summarize(ages, volumes, heights, flow_in: float, flow_out: float) -> dict:
    """局部空气龄 s、单元体积 m³、中心高度 m 与进出口体积流量 m³/s。"""
    a = np.asarray(ages, dtype=float)
    v = np.asarray(volumes, dtype=float)
    z = np.asarray(heights, dtype=float)
    if (
        a.ndim != 1
        or a.size == 0
        or a.shape != v.shape
        or a.shape != z.shape
        or not np.all(np.isfinite(a))
        or not np.all(np.isfinite(v))
        or not np.all(np.isfinite(z))
        or (a < 0).any()
        or (v <= 0).any()
        or min(flow_in, flow_out) <= 0
    ):
        raise ValueError("场数据或流量无效")
    mask = (z >= 0.1) & (z <= 1.8)
    if not mask.any():
        raise ValueError("没有呼吸区单元")
    volume = float(v.sum())
    mean = float(np.average(a, weights=v))
    breathing = float(np.average(a[mask], weights=v[mask]))
    nominal = volume / flow_in
    return {
        "cells": len(a),
        "volume_m3": volume,
        "average_age_s": mean,
        "breathing_age_s": breathing,
        "nominal_age_s": nominal,
        "air_change_efficiency": air_change_efficiency(nominal, mean),
        "flow_in_m3_s": flow_in,
        "flow_out_m3_s": flow_out,
        "mass_balance_relative": abs(flow_in - flow_out) / flow_in,
    }


def patch_flux(path: Path, patch: str) -> float:
    """读取 OpenFOAM ASCII 面通量文件的指定边界通量总和 m³/s。"""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", patch):
        raise ValueError("边界名称无效")
    text = Path(path).read_text()
    m = re.search(r"\b" + re.escape(patch) + r"\s*\{([^{}]*)\}", text, re.DOTALL)
    if not m:
        raise ValueError("未找到边界")
    block = m.group(1)
    data = re.search(r"value\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;", block, re.DOTALL)
    if not data:
        uniform = re.search(r"value\s+uniform\s+([^;]+);", block)
        boundary = Path(path).parent.parent / "constant/polyMesh/boundary"
        if not uniform or not boundary.is_file():
            raise ValueError("无法解析边界面通量")
        b = re.search(
            r"\b" + re.escape(patch) + r"\s*\{([^{}]*)\}", boundary.read_text(), re.DOTALL
        )
        n = re.search(r"nFaces\s+(\d+)\s*;", b.group(1)) if b else None
        if not n:
            raise ValueError("无法读取边界面数")
        return float(uniform.group(1)) * int(n.group(1))
    numbers = [float(x) for x in data.group(2).split()]
    if len(numbers) != int(data.group(1)):
        raise ValueError("通量数量不匹配")
    return sum(numbers)


def read_vtk(path: Path, flow_in: float, flow_out: float) -> dict:
    """读取单个 VTU 中局部 T（空气龄 s），以 PyVista 可选依赖提取网格。"""
    try:
        import pyvista as pv
    except ImportError as exc:
        raise RuntimeError("读取 VTU 需要可选 PyVista 环境") from exc
    mesh = pv.read(path)
    sized = mesh.compute_cell_sizes(length=False, area=False, volume=True)
    return summarize(
        sized.cell_data["T"],
        sized.cell_data["Volume"],
        sized.cell_centers().points[:, 2],
        flow_in,
        flow_out,
    )
