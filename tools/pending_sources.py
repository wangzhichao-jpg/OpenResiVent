"""汇总书稿片段中尚待核实的输入参数来源。"""

import argparse
from pathlib import Path

MARKERS = ("假设", "示例值", "读图", "需确认", "需作者确认")


def collect(root: Path):
    """只读取每个片段的输入表，按章、算例和参数逐行记录。"""
    items = []
    fragments = sorted(root.glob("ch*/ex*.md"))
    if not fragments:
        raise FileNotFoundError(f"未找到书稿片段：{root}")
    for path in fragments:
        text = path.read_text(encoding="utf8")
        table = text.split("**已知条件**", 1)[1].split("**计算**", 1)[0]
        for line in table.splitlines():
            if line.startswith("|"):
                cols = [x.strip() for x in line.strip("|").split("|")]
                if len(cols) >= 5 and any(m in cols[4] for m in MARKERS):
                    items.append((path.parent.name, path.stem, cols[0], cols[2], cols[3], cols[4]))
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fragments", type=Path, default=Path("build/book_fragments"))
    parser.add_argument("--out", type=Path, default=Path("build/待确认参数清单.md"))
    args = parser.parse_args()
    rows = collect(args.fragments)
    lines = [
        "# 待确认参数清单",
        "",
        "发布前须逐项核对正式来源。",
        f"条目数：{len(rows)}",
        "",
        "| 章节 | 算例 | 参数 | 数值 | 单位 | 来源 |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"{len(rows)} 项：{args.out}")


if __name__ == "__main__":
    main()
