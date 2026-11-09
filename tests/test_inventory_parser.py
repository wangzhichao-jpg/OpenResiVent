"""台账解析器对格式碎片和数据行的测试。"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_extract_numeric_rows_and_exponents(tmp_path):
    spec = importlib.util.spec_from_file_location("inventory", ROOT / "tools/book_inventory.py")
    inv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inv)
    for chapter in range(1, 7):
        (tmp_path / f"ch{chapter:02}.md").write_text("# 章\n", encoding="utf8")
    (tmp_path / "ch01.md").write_text(
        "# 章\nCO$_{2}$，单位 h$^{-1}$，数值 1.5×10$^{-3}$。\n| 类别 | 文字 |\n| -- | -- |\n| 流量 | 30 m³/h |\n",
        encoding="utf8",
    )
    inv.BOOK = tmp_path
    rows = inv.inventory()
    assert not [x for x in rows if x["kind"] == "inline_formula"]
    assert [x["value"] for x in rows if x["kind"] == "scientific_number"] == ["1.5e-3"]
    assert len([x for x in rows if x["kind"] == "table_row"]) == 1
