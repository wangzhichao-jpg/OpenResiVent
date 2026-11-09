"""五个 P3 算例及片段端到端回归。"""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "chapter,ident",
    [
        ("ch02", "ex2-07"),
        ("ch02", "ex2-08"),
        ("ch03", "ex3-02"),
        ("ch03", "ex3-04"),
        ("ch04", "ex4-10"),
    ],
)
def test_case(tmp_path, chapter, ident):
    p = ROOT / "cases/book" / chapter / f"{ident}.yaml"
    result = CliRunner().invoke(app, ["run", str(p), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.exception
    x = json.loads((tmp_path / f"{ident}.json").read_text())
    text = (tmp_path / f"{ident}.md").read_text()
    assert len(x["provenance"]["input_sha256"]) == 64
    assert "敏感性说明" in text and "| 参数 | 符号 | 数值 | 单位 | 来源 |" in text
    assert not re.search(r"\u5de5\u4f5c\u6307\u4ee4|WO-|\u004d\u0053\u0047\u002d|\u9a8c\u6536\u65b9|\u7ba1\u7406\u7aef|(?:GBT|JGJT|GB)\d{3,}-\d{4}:", text)
    if ident == "ex2-07":
        assert x["single_m3_s"] == pytest.approx(0.142923, rel=1e-5)
        assert x["double"]["flow_m3_s"] == pytest.approx(0.303185, rel=1e-5)
        assert x["book_single"] == pytest.approx(0.6) and "量纲待核" in text
    if ident == "ex3-04":
        assert not x["suitability"]["turbine_better_than_static"]
    if ident == "ex4-10":
        assert not x["check"]["pollution_passed"]
