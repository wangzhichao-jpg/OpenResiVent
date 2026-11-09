"""\u5de5\u4f5c\u6307\u4ee4书稿算例的解析目标与命令行回归。"""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[2]
TARGETS = yaml.safe_load((ROOT / "cases/benchmarks/targets.yaml").read_text(encoding="utf8"))[
    "P1_cases"
]


@pytest.mark.parametrize(
    ("name", "chapter"),
    [
        ("ex1-01", "ch01"),
        ("ex2-01", "ch02"),
        ("ex2-02", "ch02"),
        ("ex2-03", "ch02"),
        ("ex2-04", "ch02"),
        ("ex2-06", "ch02"),
        ("ex6-01", "ch06"),
        ("ex6-02", "ch06"),
        ("ex6-03", "ch06"),
        ("ex6-04", "ch06"),
        ("ex6-05", "ch06"),
    ],
)
def test_p1_case_target(name, chapter, tmp_path):
    output = CliRunner().invoke(
        app, ["run", str(ROOT / "cases/book" / chapter / (name + ".yaml")), "--out", str(tmp_path)]
    )
    assert output.exit_code == 0, output.exception
    r = json.loads((tmp_path / (name + ".json")).read_text(encoding="utf8"))
    value = {
        "ex1-01": lambda: r["international"]["ashrae_m3_s"] * 1000,
        "ex2-01": lambda: r["flow_m3_s"] * 3600,
        "ex2-02": lambda: r["bedrooms"][0]["D"] * 3600,
        "ex2-03": lambda: r["design"] * 3600,
        "ex2-04": lambda: r["target_time_s"] / 3600,
        "ex2-06": lambda: r["teq_kg_m3"] * 1e12,
        "ex6-01": lambda: r["two_point_s_1"] * 3600,
        "ex6-02": lambda: r["efficiency"],
        "ex6-03": lambda: r["injection_flow_m3_s"] * 3600,
        "ex6-04": lambda: r["duct_m3_s"] * 3600,
        "ex6-05": lambda: r["total_flow"]["deviation"],
    }[name]()
    assert value == pytest.approx(TARGETS[name]["value"], abs=0.005 if name == "ex6-02" else 1e-8)
    assert (tmp_path / (name + ".md")).is_file()
