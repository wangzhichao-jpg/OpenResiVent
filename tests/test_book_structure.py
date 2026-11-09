"""四段式、原始演算保存及待确认项提取。"""

import subprocess
import sys
from pathlib import Path

from openresivent import __version__
from openresivent.report.book import render_book

ROOT = Path(__file__).resolve().parents[1]


def test_standard_source_only_for_matching_value():
    from openresivent.report.markdown import _input_rows

    inputs = {"limit_ppm": 1000, "limit_ppm_source": "GB/T 18883-2022 第4.2条、表1"}
    assert "GB/T 18883-2022 第4.2条、表1" in _input_rows(inputs, "ventrate")[0]
    inputs["limit_ppm"] = 900
    assert "假设，需作者确认" in _input_rows(inputs, "ventrate")[0]


def test_four_sections_and_appendix_source(tmp_path):
    full = "| 参数 | 符号 | 数值 | 单位 | 来源 |\n|---|---|---|---|---|\n| 面积 | $A$ | 10 | m² | 假设，需作者确认 |\n\n**第一步：计算。**\n\n$$Q=10\\times 2=20$$\n\n| 房间 | 风量 |\n|---|---|\n| 卧室1 | 20 |\n\n结果：20 m³/h。\n本例不涉及条文判定。\n"
    text = render_book("示例", "ex2-01", "ch02", full, {})
    labels = ["**已知条件**", "**计算**", "**结果**", "**条文对照**"]
    assert [text.index(x) for x in labels] == sorted(text.index(x) for x in labels)
    assert "| 房间 | 风量 |" not in text and "第一步" not in text
    assert (
        f"本算例由 OpenResiVent v{__version__} 计算，算例文件 cases/book/ch02/ex2-01.yaml" in text
    )
    fragments = tmp_path / "fragments/ch02"
    fragments.mkdir(parents=True)
    (fragments / "ex2-01.md").write_text(text, encoding="utf8")
    output = tmp_path / "sources.md"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/pending_sources.py"),
            "--fragments",
            str(fragments.parent),
            "--out",
            str(output),
        ],
        check=True,
    )
    assert "条目数：1" in output.read_text(encoding="utf8")
