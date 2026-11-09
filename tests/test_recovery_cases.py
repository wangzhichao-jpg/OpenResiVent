"""四个 M4 算例从 YAML 到 JSON 和片段的回归。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("ident", ["ex4-04", "ex4-05", "ex4-06", "ex4-12"])
def test_case(tmp_path, ident):
    path = ROOT / "cases/book/ch04" / f"{ident}.yaml"
    run = CliRunner().invoke(app, ["run", str(path), "--out", str(tmp_path)])
    assert run.exit_code == 0, run.exception
    payload = json.loads((tmp_path / f"{ident}.json").read_text(encoding="utf8"))
    text = (tmp_path / f"{ident}.md").read_text(encoding="utf8")
    assert len(payload["provenance"]["input_sha256"]) == 64
    assert "敏感性说明" in text and "| 参数 | 符号 | 数值 | 单位 | 来源 |" in text
    assert "\x0c" not in text
    if ident == "ex4-04":
        assert "| 捕集效率 | $E$ | 100 | % |" in text
    if ident == "ex4-05":
        assert "| 初始显热效率 | $\\eta_s$ | 75 | % |" in text
    if ident == "ex4-04":
        assert payload["doubling_dust_kg"] * 1000 == pytest.approx(26.022859, rel=1e-6)
        assert payload["dynamic_figure"]["flow_ratio"] < 1
    elif ident == "ex4-05":
        assert payload["figure11_threshold_m3_s"] * 3600 == pytest.approx(63.6)
        assert payload["figure10_threshold_m3_s"] * 3600 == pytest.approx(170)
    elif ident == "ex4-06":
        assert not payload["near_zero"]["passed"] and payload["general"]["passed"]
        assert set(payload["provenance"]["rule_packs"]) == {"GBT21087-2020", "GBT51350-2019"}
    else:
        assert payload["result"]["replace_recommended"]
