"""读取已完成外部算例，计算体积加权指标与 GCI；不启动 CFD。"""

import json
import re
import sys

from openresivent.cfd.config import case_root
from openresivent.cfd.postprocess import patch_flux, read_vtk
from openresivent.cfd.template import gci

ROOT = case_root()


def main():
    """输出可复算的 CFD 指标 JSON 到 CFD 工作目录。"""
    output = {}
    for kind in ("upper", "lower"):
        rows = []
        for scale in (1, 2, 4):
            name = f"first-order-{kind}-{scale}" + ("-continued" if scale > 1 else "")
            p = ROOT / name
            log = (p / "log.simpleFoam").read_text()
            converged = bool(re.search(r"SIMPLE solution converged", log))
            scalar = (p / "log.scalar").read_text()
            if "End" not in scalar:
                raise RuntimeError("标量尚未完成")
            result = read_vtk(
                next(p.glob("VTK/*/internal.vtu")),
                -patch_flux(p / "0/phi", "inlet"),
                patch_flux(p / "0/phi", "outlet"),
            )
            result.update(
                {
                    "case": name,
                    "flow_converged": converged,
                    "scalar_log": re.findall(r"Final residual = ([0-9.eE+-]+)", scalar)[-1],
                }
            )
            rows.append(result)
        try:
            convergence = gci([x["average_age_s"] for x in rows], 2)
        except ValueError as exc:
            convergence = {"error": str(exc)}
        if "gci_fine" in convergence and all(x["flow_converged"] for x in rows):
            rows[-1]["gci_fine"] = convergence["gci_fine"]
        p = ROOT / rows[-1]["case"]
        (p / "summary.json").write_text(json.dumps(rows[-1], ensure_ascii=False, indent=2) + "\n")
        output[kind] = {"rows": rows, "gci": convergence}
    target = ROOT / "first-order-convergence.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    sys.exit(main())
