"""在 build 中生成 P2 第 3、5 章书稿预览；书稿原件只读。"""

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path

from openresivent.core.case import load_case
from openresivent.core.runner import execute
from openresivent.report.markdown import render

ROOT = Path(__file__).resolve().parents[1]


def embed(raw: str, ident: str, snippet: str) -> str:
    """原稿定位已知区间；标记之外保留原文。"""
    if ident == "ex5-01":
        start = raw.index("**计算示例：**", raw.index("### 5.2.1"))
        end = raw.index("**表5-2**", start)
        prefix = "**计算示例：**\n\n"
    elif ident == "ex5-02":
        start = raw.index("**计算示例：**", raw.index("### 5.3.1"))
        end = raw.index("对于底层用户", start)
        prefix = "**计算示例：**\n\n"
    elif ident == "ex3-03":
        start = end = raw.index("### 3.5.3")
        prefix = "**计算示例：气密性与自然渗透**\n\n"
    elif ident == "ex5-07":
        start = end = raw.index("## 本章小结")
        prefix = "## 5.5 户内新风系统与油烟机压差耦合\n\n**计算示例：**\n\n"
    else:
        raise ValueError("未知算例")
    return (
        raw[:start]
        + f"<!-- resivent:{ident} -->\n\n"
        + prefix
        + snippet.rstrip()
        + f"\n\n<!-- /resivent:{ident} -->\n\n"
        + raw[end:]
    )


def main():
    """按书稿位置创建预览、差异及输入锁；不覆盖书稿。"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--book-dir",
        type=Path,
        default=Path(os.environ.get("ORV_BOOK_DIR", ROOT / "external-book-not-provided")),
    )
    parser.add_argument("--out", type=Path, default=ROOT / "build/p2_book_preview")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    digest = lambda b: hashlib.sha256(b).hexdigest()
    manifest = {}
    for chapter, identifiers in [("ch03", ["ex3-03"]), ("ch05", ["ex5-01", "ex5-02", "ex5-07"])]:
        raw = (args.book_dir / f"{chapter}.md").read_text(encoding="utf8")
        preview = raw
        for ident in identifiers:
            path = ROOT / "cases/book" / chapter / f"{ident}.yaml"
            case = load_case(path)
            result, _ = execute(case, path)
            snippet = render(case.meta.title, case.module, case.input, result)
            (args.out / f"{ident}.md").write_text(snippet, encoding="utf8")
            preview = embed(preview, ident, snippet)
            manifest[ident] = {
                "input_sha256": digest(path.read_bytes()),
                "fragment_sha256": digest(snippet.encode()),
            }
        (args.out / f"{chapter}.md").write_text(preview, encoding="utf8")
        (args.out / f"{chapter}.diff").write_text(
            "".join(
                difflib.unified_diff(
                    raw.splitlines(keepends=True),
                    preview.splitlines(keepends=True),
                    fromfile=f"original/{chapter}.md",
                    tofile=f"preview/{chapter}.md",
                )
            ),
            encoding="utf8",
        )
        manifest[chapter] = {
            "original_sha256": digest(raw.encode()),
            "preview_sha256": digest(preview.encode()),
        }
    (args.out / "book.lock").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )


if __name__ == "__main__":
    main()
