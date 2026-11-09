"""书稿片段体例与两种甲醛工况回归。"""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    "ch01/ex1-01",
    "ch02/ex2-01",
    "ch02/ex2-02",
    "ch02/ex2-03",
    "ch02/ex2-04",
    "ch02/ex2-06",
    "ch06/ex6-01",
    "ch06/ex6-02",
    "ch06/ex6-03",
    "ch06/ex6-04",
    "ch06/ex6-05",
]


@pytest.mark.parametrize("name", CASES)
def test_fragment_style(name, tmp_path):
    case = ROOT / "cases/book" / (name + ".yaml")
    out = CliRunner().invoke(app, ["run", str(case), "--out", str(tmp_path)])
    assert out.exit_code == 0, out.exception
    fragment = (tmp_path / (case.stem + ".md")).read_text()
    assert "| 参数 | 符号 | 数值 | 单位 | 来源 |" in fragment
    assert "### " not in fragment
    assert (r"\tag{2-4}" in fragment) == (case.stem == "ex2-01")
    table = fragment.split("| 参数 | 符号 | 数值 | 单位 | 来源 |", 1)[1].split("**计算**", 1)[0]
    table = "| 参数 | 符号 | 数值 | 单位 | 来源 |" + table
    assert "occupants" not in table and "height_m" not in table
    metadata = yaml.safe_load((ROOT / "data/param_meta.yaml").read_text())
    for line in table.splitlines()[2:]:
        if not line.strip():
            continue
        fields = [field.strip() for field in line.strip("|").split("|")]
        matching = [
            v
            for v in metadata.values()
            if v["name"] == fields[0] and "$" + v["symbol"] + "$" == fields[1]
        ]
        if not matching and fields[0].endswith("面积"):
            matching = [metadata["area_m2"]]
        assert matching and any(v["unit"] == fields[3] for v in matching)
        assert "1e+03" not in fields[2]
        if fields[3] == "—":
            assert any(v.get("dimensionless") is True for v in matching)
    assert "selected" not in fragment and "GBT18883" not in fragment
    assert "限值须按输入计算" not in fragment
    if case.stem in ("ex1-01", "ex2-02", "ex2-03"):
        assert "| 净高 | $h$ | 2.8 | m |" in table
        assert "| 居住面积 | $F$ |" in table
        assert "| 卧室1面积 | $A_{1}$ |" in table
    assert all(x in fragment for x in ("**已知条件**", "**计算**", "**结果**", "**条文对照**"))
    assert "**第一步：" not in fragment
    if case.stem == "ex2-01":
        assert "满足 GB/T 18883-2022 表 1" in fragment
        assert "不满足 GB/T" not in fragment
        assert "90000" in fragment
    if case.stem == "ex6-01":
        assert "7.863" in fragment and "7.003" in fragment
        assert "1.72" in fragment
        assert "point_1" not in fragment and "0.800" not in fragment
    if case.stem == "ex2-02":
        data = json.loads((tmp_path / "ex2-02.json").read_text())
        assert data["bedrooms"][0]["selected"] * 3600 == pytest.approx(30)
        assert data["hcho_example"]["selected"] * 3600 == pytest.approx(3 / 0.07)
        assert "由甲醛法控制" in fragment and "需作者确认" in fragment
