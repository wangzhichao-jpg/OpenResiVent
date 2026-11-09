"""\u0057\u004f\u002d\u00502-01 四个书稿算例从 YAML 至 JSON/片段的端到端校核。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.core.p2_examples import run_fan

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "chapter,case", [("ch05", "ex5-01"), ("ch05", "ex5-02"), ("ch05", "ex5-07"), ("ch03", "ex3-03")]
)
def test_case_cli(tmp_path, chapter, case):
    source = ROOT / "cases/book" / chapter / (case + ".yaml")
    run = CliRunner().invoke(app, ["run", str(source), "--out", str(tmp_path)])
    assert run.exit_code == 0, run.exception
    result = json.loads((tmp_path / (case + ".json")).read_text())
    fragment = (tmp_path / (case + ".md")).read_text()
    assert len(result["provenance"]["input_sha256"]) == 64
    assert result["provenance"]["git_commit"]
    assert "| 参数 | 符号 | 数值 | 单位 | 来源 |" in fragment
    assert "**计算**" in fragment and "本例不涉及条文对照" in fragment
    assert "敏感性说明" in fragment
    if case == "ex5-01":
        assert result["stack"]["total_pressure_pa"] == pytest.approx(134.663, abs=0.001)
        assert result["stack"]["neutral_height_m"] == pytest.approx(47.303613, rel=1e-6)
        assert result["stack"]["simplified_pa"] == 120
        assert result["flows"][0]["delta_p"] == pytest.approx(63.700494, rel=1e-6)
        assert result["flows"][1]["delta_p"] == pytest.approx(70.962568, rel=1e-6)
    elif case == "ex5-02":
        assert result["fraction"] * 100 == pytest.approx(53.452248, rel=1e-6)
    elif case == "ex5-07":
        assert set(result["scenarios"]) == {"1.0", "0.6"}
        for scenarios in result["scenarios"].values():
            assert set(scenarios) == {
                "no_makeup",
                "interlock",
                "opening",
                "opening_kitchen",
                "mechanical_living",
                "mechanical_kitchen",
            }
            assert scenarios["opening_kitchen"]["device_rooms"]["opening"] == "kitchen"
            assert scenarios["mechanical_kitchen"]["device_rooms"]["makeup"] == "kitchen"
            assert (
                scenarios["opening_kitchen"]["pressures_pa"]["kitchen"]
                > scenarios["opening"]["pressures_pa"]["kitchen"]
            )
            assert scenarios["interlock"]["fresh_exhaust_m3_s"] == 0
            assert scenarios["opening"]["opening_m3_s"] > 0
            assert all(v["mass_residual_kg_s"] < 1e-10 for v in scenarios.values())
            assert (
                scenarios["opening"]["pressures_pa"]["kitchen"]
                > scenarios["no_makeup"]["pressures_pa"]["kitchen"]
            )
    else:
        assert 0 < result["design"]["air_change_per_s"] * 3600 < 0.1
        assert (
            result["sensitivity"]["5"]["air_change_per_s"]
            > result["sensitivity"]["1"]["air_change_per_s"]
        )
        assert "低于该多数区间" in fragment


@pytest.mark.parametrize(
    ("ident", "raw", "outside"),
    [
        ("ex5-01", "前### 5.2.1\n**计算示例：**旧\n**表5-2**后", "**表5-2**后"),
        ("ex5-02", "前### 5.3.1\n**计算示例：**旧\n对于底层用户后", "对于底层用户后"),
        ("ex3-03", "前### 3.5.3后", "### 3.5.3后"),
        ("ex5-07", "前## 本章小结后", "## 本章小结后"),
    ],
)
def test_preview_markers(ident, raw, outside):
    import importlib.util

    spec = importlib.util.spec_from_file_location("preview_p2", ROOT / "tools/preview_p2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = module.embed(raw, ident, "演算片段")
    assert f"<!-- resivent:{ident} -->" in output
    assert f"<!-- /resivent:{ident} -->" in output
    assert output.endswith(outside)
    assert "演算片段" in output


def test_fan_invalid_and_limits():
    with pytest.raises(ValueError):
        run_fan({"free_flow_m3_h": 400, "shutoff_pressure_pa": 280, "back_pressure_pa": 281})
    assert run_fan({"free_flow_m3_h": 400, "shutoff_pressure_pa": 280, "back_pressure_pa": 0})[
        "fraction"
    ] == pytest.approx(1)
