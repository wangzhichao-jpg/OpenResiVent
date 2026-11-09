"""二阶 CFD 外部结果重算：读取本机 CFD 目录，不启动求解。"""

import json
import re

import numpy as np

from openresivent.cfd.config import case_root
from openresivent.cfd.postprocess import patch_flux, read_vtk
from openresivent.cfd.template import oscillatory_uncertainty

ROOT = case_root()


def evaluate(kind: str) -> dict:
    """核验每个网格最后迭代残差、监测值及空气龄，返回不确定度。"""
    rows = []
    for i in (1, 2, 4):
        flow = ROOT / (
            f"second-order-{kind}-{i}-" + ("monitor3" if kind == "upper" and i == 2 else "monitor2")
        )
        age = ROOT / (
            f"second-order-{kind}-{i}-"
            + (
                "age-polish"
                if i == 4
                else "age-monitor3"
                if kind == "upper" and i == 2
                else "age-monitor"
            )
        )
        segment = re.split(r"(?m)^Time = ", (flow / "log.simpleFoam").read_text())[-1]
        residuals = [float(x) for x in re.findall(r"Initial residual = ([\deE.+-]+)", segment)]
        m = np.loadtxt(flow / "postProcessing/volumeStats/0/volFieldValue.dat")
        m = m[m[:, 0] >= m[-1, 0] - 1000]
        variances = np.ptp(m[:, 1:], axis=0) / np.abs(m[:, 1:].mean(axis=0))
        p = np.loadtxt(flow / "postProcessing/outletPressure/0/surfaceFieldValue.dat")
        p = p[p[:, 0] >= p[-1, 0] - 1000]
        p_delta = np.ptp(p[:, 1])
        a = np.loadtxt(age / "postProcessing/ageAverage/0/volFieldValue.dat")
        a = a[a[:, 0] >= a[-1, 0] - 500]
        age_delta = np.ptp(a[:, 1]) / abs(a[:, 1].mean())
        ars = [
            float(x)
            for x in re.findall(
                r"Initial residual = ([\deE.+-]+)", (age / "log.scalar").read_text()
            )
        ]
        if (
            len(residuals) != 6
            or max(residuals) >= 1e-5
            or np.max(variances) >= 0.001
            or p_delta > 1e-12
            or ars[-1] >= 1e-8
            or age_delta >= 0.0001
        ):
            raise ValueError(f"{kind} 网格{i}未满足监测判据")
        raw = read_vtk(
            next(age.glob("VTK/*/internal.vtu")),
            -patch_flux(age / "0/phi", "inlet"),
            patch_flux(age / "0/phi", "outlet"),
        )
        raw.update(
            {
                "flow_residual_max": max(residuals),
                "flow_monitor_range": variances.tolist(),
                "outlet_pressure_range_pa_kinematic": p_delta,
                "age_residual": ars[-1],
                "age_monitor_range": age_delta,
                "flow_converged": True,
                "case": age.name,
            }
        )
        rows.append(raw)
    uncertainty = oscillatory_uncertainty([x["air_change_efficiency"] for x in rows])
    if uncertainty["relative_fine"] >= 0.05:
        raise ValueError("网格不确定度超限")
    rows[-1]["oscillatory_uncertainty_relative"] = uncertainty["relative_fine"]
    (ROOT / rows[-1]["case"] / "summary.json").write_text(
        json.dumps(rows[-1], ensure_ascii=False, indent=2) + "\n"
    )
    return {"rows": rows, "uncertainty": uncertainty}


def main():
    output = {k: evaluate(k) for k in ("upper", "lower")}
    path = ROOT / "second-order-verified.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
