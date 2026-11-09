"""逐算例检查书稿四段式及未删节附录。"""

import os
import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from openresivent import __version__
from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[1]
CASES = sorted((ROOT / "cases/book").glob("ch*/ex*.yaml"))


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.stem)
def test_all_book_fragment_structure(case, tmp_path):
    data = yaml.safe_load(case.read_text(encoding="utf8"))
    if data["module"] in (
        "energy_control",
        "energy_erv",
        "vav_comparison",
        "natural_cooling",
    ) and not os.environ.get("ORV_WEATHER_DIR"):
        pytest.skip("未配置气象数据")
    if data["module"] == "cfd_compare" and not os.environ.get("ORV_CFD_DIR"):
        pytest.skip("未配置 CFD 数据")
    result = CliRunner().invoke(app, ["run", str(case), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.exception
    text = (tmp_path / f"{case.stem}.md").read_text(encoding="utf8")
    labels = ["**已知条件**", "**计算**", "**结果**", "**条文对照**"]
    assert all(text.count(x) == 1 for x in labels)
    assert [text.index(x) for x in labels] == sorted(text.index(x) for x in labels)
    assert "| 参数 | 符号 | 数值 | 单位 | 来源 |" in text
    assert text.count("| 参数 | 符号 | 数值 | 单位 | 来源 |") == 1
    assert not re.search(
        r"第[一二三四五六七八九十]+步|合成禁词|(?:GBT|JGJT|GB)\d{3,}-\d{4}:",
        text,
    )
    assert len(re.findall(r"^\|[\s:|\-]+\|$", text, re.MULTILINE)) == (
        3 if case.stem == "ex5-07" else 1
    )
    calculation = text.split("**计算**", 1)[1].split("**结果**", 1)[0]
    assert len(re.findall(r"^-\s*卧室\s*\d+\s*[：:]", calculation, re.MULTILINE)) <= 1
    assert len(re.findall(r"^-\s*路径\s*\d+\s*[：:]", calculation, re.MULTILINE)) <= 1
    assert text.rstrip().endswith(
        f"本算例由 OpenResiVent v{__version__} 计算，算例文件 cases/book/{case.parent.name}/{case.stem}.yaml"
    )
    full = (tmp_path / ".appendix" / f"{case.stem}.md").read_text(encoding="utf8")
    assert full and "| 参数 | 符号 | 数值 | 单位 | 来源 |" in full
