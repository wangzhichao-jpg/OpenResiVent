"""外部 CFD 后处理结果用于书稿算例，不调用或链接 OpenFOAM。"""

import hashlib
import json

from openresivent.cfd.config import case_root


def comparison(data: dict) -> dict:
    """从 CFD 目录读取两份已核验的 JSON 指标。"""
    base = case_root()
    result = {}
    for name in ("upper", "lower"):
        path = (base / data[name]).resolve()
        if not path.is_relative_to(base):
            raise ValueError("结果路径不得越出 CFD 目录")
        raw = path.read_bytes()
        row = json.loads(raw)
        if not 0 < row["air_change_efficiency"] <= 1:
            raise ValueError("换气效率超出物理范围")
        if row.get("mass_balance_relative", float("inf")) >= 1e-4:
            raise ValueError("CFD 质量流量未通过守恒检查")
        if row.get("flow_converged") is not True:
            raise ValueError("CFD 流场未收敛，拒绝用于书稿算例")
        uncertainty = row.get("gci_fine", row.get("oscillatory_uncertainty_relative", float("inf")))
        if uncertainty >= 0.05:
            raise ValueError("CFD 网格不确定度未通过，拒绝用于书稿算例")
        result[name] = {**row, "sha256": hashlib.sha256(raw).hexdigest()}
    return result
