"""只读扫描书稿中的计算线索；生成候选台账，须人工核验。"""

import argparse
import csv
import os
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOK = Path(os.environ.get("ORV_BOOK_DIR", ROOT / "external-book-not-provided"))
DEST = ROOT / "build/inventory"
FIELDS = [
    "item_id",
    "chapter",
    "section",
    "line",
    "kind",
    "text",
    "value",
    "unit",
    "calc_type_guess",
    "source_guess",
    "case_id",
    "note",
]
VALUE = re.compile(
    r"(?<![\w.])([-+−]?\d+(?:\.\d+)?)\s*(m³/\(h·m²\)|m³/\(h·人\)|m³/h|m³/s|m³|m²|mg/m³|μg/m³|ppm|Pa|℃|°C|%|h⁻¹|天|d)(?![A-Za-z/])"
)
FIGURE = re.compile(r"图\s*\d+[-.．–]\d+")
INLINE = re.compile(r"(?<!\$)\$(?!\$)([^$\n]*\d[^$\n]*)\$(?!\$)")
SECTION = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+)+)")
SCIENTIFIC = re.compile(
    r"(?<![\w.])(?P<mantissa>\d+(?:\.\d+)?)\s*[×x] ?10\$\^\{?(?P<exponent>[-−+]?\d+)\}?\$"
)


def inventory() -> list[dict]:
    """读取第 1–6 章并返回候选条目；行号为书稿行号。"""
    items = []
    for chapter in range(1, 7):
        lines = (BOOK / f"ch{chapter:02}.md").read_text(encoding="utf8").splitlines()
        section = ""
        formula = []
        formula_line = 0
        in_formula = False
        for number, line in enumerate(lines, 1):
            heading = SECTION.match(line)
            if heading:
                section = heading.group(1)
            matches = []
            if "$$" in line:
                parts = line.split("$$")
                for idx, part in enumerate(parts):
                    if in_formula:
                        formula.append(part)
                    if idx < len(parts) - 1:
                        if in_formula:
                            matches.append(("formula", " ".join(formula), "", "", formula_line))
                            formula = []
                        else:
                            formula_line = number
                        in_formula = not in_formula
            elif in_formula:
                formula.append(line)
            else:
                for match in INLINE.finditer(line):
                    expr = match.group(1).strip()
                    if re.fullmatch(r"[_^]\s*\{?[-+]?\d+(?:\.\d+)?\}?", expr):
                        continue
                    matches.append(("inline_formula", match.group(0), "", "", number))
                for match in SCIENTIFIC.finditer(line):
                    exponent = match.group("exponent").replace("−", "-")
                    matches.append(
                        (
                            "scientific_number",
                            match.group(0),
                            f"{match.group('mantissa')}e{exponent}",
                            "",
                            number,
                        )
                    )
                for match in VALUE.finditer(line):
                    matches.append(
                        ("quantity", match.group(0), match.group(1), match.group(2), number)
                    )
                for match in FIGURE.finditer(line):
                    matches.append(("figure", match.group(0), "", "", number))
                if line.lstrip().startswith("|") and re.search(r"\d", line):
                    matches.append(("table_row", line.strip(), "", "", number))
                if "计算示例" in line or "计算实例" in line:
                    matches.append(("example", "计算示例或实例（详见原文定位）", "", "", number))
            for kind, text, value, unit, source_line in matches:
                kind_guess = "D" if chapter == 6 else "C" if chapter == 3 else "A"
                source_guess = "文献" if re.search(r"\[\d+\]", line) else "待定"
                items.append(
                    {
                        "item_id": f"BK{chapter:02}-{len(items) + 1:05}",
                        "chapter": f"ch{chapter:02}",
                        "section": section,
                        "line": source_line,
                        "kind": kind,
                        "text": text,
                        "value": value,
                        "unit": unit,
                        "calc_type_guess": kind_guess,
                        "source_guess": source_guess,
                        "case_id": "待分配",
                        "note": "候选，需人工复核",
                    }
                )
    return items


def main() -> None:
    """生成 CSV 和计数汇总；不修改书稿。"""
    global BOOK
    parser = argparse.ArgumentParser()
    parser.add_argument("--book-dir", type=Path, default=BOOK)
    BOOK = parser.parse_args().book_dir
    if not BOOK.is_dir():
        parser.error(f"书稿目录不存在：{BOOK}")
    DEST.mkdir(parents=True, exist_ok=True)
    rows = inventory()
    with (DEST / "book_calc_inventory.csv").open("w", encoding="utf8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    chapters, kinds = Counter(x["chapter"] for x in rows), Counter(x["kind"] for x in rows)
    summary = [
        "# 书稿计算线索台账（候选）",
        "",
        "本清点为启发式，改进前 1155 条（示例），改进后 "
        + str(len(rows))
        + " 条；新版固定种子抽样见《抽样复核_P1.md》，历史旧版见《抽样复核.md》。台账在 v1.0 前不对外公开。",
        "",
        "按章：",
    ]
    summary.extend(f"- {k}: {v}" for k, v in sorted(chapters.items()))
    summary.append("\n按条目类型：")
    summary.extend(f"- {k}: {v}" for k, v in sorted(kinds.items()))
    summary.append(
        "\n分类规则：第 6 章暂标 D，第 3 章暂标 C，其他暂标 A；带引用标记的行暂标文献，其余待定。不能据此判断真实类型或溯源。"
    )
    sample = random.Random(440).sample(rows, min(20, len(rows)))
    sample_results = []
    for row in sample:
        text = (
            (BOOK / (row["chapter"] + ".md"))
            .read_text(encoding="utf8")
            .splitlines()[row["line"] - 1]
        )
        if row["kind"] == "formula":
            valid = "$$" in text
        elif row["kind"] == "table_row":
            valid = text.lstrip().startswith("|")
        elif row["kind"] == "example":
            valid = "计算示例" in text or "计算实例" in text
        else:
            valid = row["text"] in text
        sample_results.append((row["item_id"], valid))
    failures = sum(not valid for _, valid in sample_results)
    summary.append(
        f"\n自动位置抽样（随机种子 440，{len(sample_results)} 条）：位置或类型线索不匹配 {failures} 条，点估计 {failures / len(sample_results):.0%}。样本条目：{', '.join(x for x, _ in sample_results)}。这是机器检查位置及字面线索，不代表领域分类、数值正确性或漏检率；小样本零错误时仍不能证明总体错误率为零，需人工复核。"
    )
    summary.append("\n## 方案 2.3 六项问题的候选定位")
    groups = [
        ("滤网周期 71 天及表中约 97 天", [("ch04", 427, 427), ("ch04", 470, 470)]),
        ("100 m 热压与 40 Pa", [("ch05", 87, 95)]),
        ("ASHRAE 62.2 / 62.1 公式混用", [("ch01", 206, 206)]),
        ("表格 N/A", [("ch04", 469, 471)]),
        ("居室机械通风经验式出处", [("ch02", 518, 520)]),
        ("积尘衰减式与系数", [("ch04", 432, 434)]),
    ]
    for title, spans in groups:
        found = [
            r["item_id"]
            for r in rows
            if any(r["chapter"] == ch and lo <= r["line"] <= hi for ch, lo, hi in spans)
        ]
        summary.append(f"- {title}：{', '.join(found) if found else '未找到候选，需人工补录'}。")
    (DEST / "台账汇总.md").write_text("\n".join(summary) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
