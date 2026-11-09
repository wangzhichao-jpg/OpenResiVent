"""给定均匀通道的空气龄与解析解比较；不启动外部求解器。"""

import json

import numpy as np

from openresivent.cfd.config import case_root


def channel_error(positions, ages, speed: float) -> dict:
    """单元中心坐标 m、空气龄 s、给定速度 m/s → 各项解析误差。"""
    x = np.asarray(positions, dtype=float)
    age = np.asarray(ages, dtype=float)
    if (
        x.ndim != 1
        or x.size == 0
        or x.shape != age.shape
        or not np.isfinite(speed)
        or speed <= 0
        or not np.all(np.isfinite(x))
        or not np.all(np.isfinite(age))
        or np.any(x <= 0)
        or np.any(age < 0)
    ):
        raise ValueError("通道坐标、空气龄或速度无效")
    first = x.min()
    after_first = x > first + max(1e-7, abs(first) * 1e-6)
    if not after_first.any():
        raise ValueError("通道至少需要两个不同中心截面")
    err = np.abs(age - x / speed) / (x / speed)
    return {
        "first_age_s": float(np.mean(age[~after_first])),
        "last_age_s": float(np.mean(age[np.isclose(x, x.max(), rtol=0, atol=1e-7)])),
        "max_relative_error_except_first": float(err[after_first].max()),
    }


def main() -> None:
    """读取迁移后的通道 VTU 并打印结果。"""
    try:
        import pyvista as pv
    except ImportError as exc:
        raise RuntimeError("读取 VTU 需要可选 PyVista 环境") from exc
    root = case_root() / "second-order-channel-linear" / "VTK"
    paths = list(root.glob("*/internal.vtu"))
    if len(paths) != 1:
        raise FileNotFoundError(f"通道 VTU 缺失或不唯一：{root}")
    mesh = pv.read(paths[0])
    print(
        json.dumps(
            channel_error(mesh.cell_centers().points[:, 0], mesh.cell_data["T"], 0.5), indent=2
        )
    )


if __name__ == "__main__":
    main()
