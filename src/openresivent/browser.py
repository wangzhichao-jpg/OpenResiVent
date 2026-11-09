"""浏览器本地计算入口，复用与命令行相同的物理内核。"""

import json
from pathlib import Path

from openresivent import __version__
from openresivent.core.case import Case
from openresivent.core.runner import execute
from openresivent.ventrate.calculation import co2_flow

SUPPORTED = frozenset({"co2", "ventrate", "dwelling_pressure", "makeup_design", "shaft"})


def calculate_json(payload: str) -> str:
    """JSON 算例文本 → JSON 计算结果，单位与命令行一致，不进行网络请求。"""
    case = Case.model_validate(json.loads(payload))
    if case.module not in SUPPORTED:
        raise ValueError("浏览器模式暂不支持此模块，请改用本机服务或命令行")
    if case.module == "co2":
        d = case.input
        generation = float(d["occupants"]) * float(d["co2_l_h_person"]) * 1e-3 / 3600
        result = {
            "flow_m3_s": co2_flow(
                generation, float(d["co2_outdoor_ppm"]) * 1e-6, float(d["co2_limit_ppm"]) * 1e-6
            )
        }
        packs = {"JGJT440-2018": "2018"}
    else:
        result, packs = execute(case, Path("/orv/case.yaml"))
    data = {
        "id": case.meta.id,
        **result,
        "provenance": {
            "software_version": __version__,
            "git_commit": "browser-local",
            "git_dirty": None,
            "rule_packs": packs,
        },
    }
    return json.dumps(data, ensure_ascii=False, allow_nan=False)
