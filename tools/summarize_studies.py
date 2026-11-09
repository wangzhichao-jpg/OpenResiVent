"""将研究扫描整理为可复核二维表；仅描述计算事实。"""

import csv
from collections import defaultdict
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    """读取 UTF-8 扫描样本表。"""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_table(path, header, body):
    """输出二维表和独立 DOCX。"""
    with path.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as stream:
        w = csv.writer(stream)
        w.writerow(header)
        w.writerows(body)
    doc = Document()
    doc.add_heading(path.stem, 0)
    doc.add_paragraph(
        "以下为指定示例模型的计算结果，设备性能、气密性及边界均须核实；不替代现场检测。"
    )
    if "竖井" in path.name:
        assumptions = [
            "稳态等温；楼层分布为低层集中。",
            "支管尺寸、粗糙度、出口及住宅气密性采用模型默认假设。",
            "风机曲线和止回阀漏风等级按示例模型取值，未使用现场实测。",
            "各组合等权，比例不代表实际建筑群体概率。",
        ]
    else:
        assumptions = [
            "住宅体积250 m³，封闭厨房，门缝和围护分配采用示例假设。",
            "新风送风150 m³/h、排风127.5 m³/h；各设备按理想定风量。",
            "机械补风和自然开口分别计算，不叠加。",
            "15 Pa 是示例提示阈值，不是燃气安全限值。",
        ]
    doc.add_heading("模型假设", level=1)
    for item in assumptions:
        doc.add_paragraph(item, style="List Bullet")
    table = doc.add_table(rows=1, cols=len(header))
    for c, s in zip(table.rows[0].cells, header, strict=True):
        c.text = str(s)
    for row in body:
        for c, v in zip(table.add_row().cells, row, strict=True):
            c.text = str(v)
    doc.save(path.with_suffix(".docx"))


def main():
    """按气密性和设备风量整理两户型补风结果。"""
    root = ROOT / "build/p309"
    data = rows(root / "makeup-study/samples.csv")
    index = {(float(x["n50_per_h"]), int(x["hood_m3_h"]), int(x["bedrooms"])): x for x in data}
    body = []
    for n in sorted({k[0] for k in index}):
        for hood in sorted({k[1] for k in index}):
            row = [n, hood]
            for bedrooms in (2, 3):
                item = index[(n, hood, bedrooms)]
                row.extend(
                    (
                        round(float(item["mechanical_m3_s"]) * 3600, 3),
                        round(float(item["opening_m2"]) * 10000, 3),
                    )
                )
            body.append(row)
    write_table(
        root / "makeup-study/补风二维表",
        [
            "n50 次/h",
            "油烟机 m³/h",
            "两卧机械 m³/h",
            "两卧开口 cm²",
            "三卧机械 m³/h",
            "三卧开口 cm²",
        ],
        body,
    )
    shaft = rows(root / "shaft-study/samples.csv")
    groups = defaultdict(list)
    for row in shaft:
        groups[(row["floors"], row["width"], row["depth"])].append(float(row["bottom_m3_s"]) * 3600)
    table = []
    for key, values in sorted(groups.items(), key=lambda x: tuple(map(float, x[0]))):
        table.append(
            [
                *key,
                len(values),
                round(min(values), 3),
                round(max(values), 3),
                sum(x >= 300 for x in values) / len(values),
            ]
        )
    write_table(
        root / "shaft-study/竖井分组表",
        ["层数", "宽 m", "深 m", "样本数", "底层最小 m³/h", "底层最大 m³/h", "达到300比例"],
        table,
    )
    print("二维汇总已生成")


if __name__ == "__main__":
    main()
