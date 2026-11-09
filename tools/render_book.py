"""生成全部算例正文和按章组织的完整演算。"""

import json
from pathlib import Path

from openresivent.cli import run

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "build/book_fragments"
    appendix = ROOT / "build/book_appendix"
    appendix.mkdir(parents=True, exist_ok=True)
    failures = []
    for chapter in sorted((ROOT / "cases/book").glob("ch*")):
        chunks = [
            f"# {chapter.name} 完整演算",
            "",
            "计算值为示例或指定工况，来源以算例和输入表为准。",
        ]
        for case in sorted(chapter.glob("ex*.yaml")):
            dest = out / chapter.name
            try:
                run(case, dest)
                full = (dest / ".appendix" / f"{case.stem}.md").read_text(encoding="utf8")
                data = json.loads((dest / f"{case.stem}.json").read_text(encoding="utf8"))
                data.pop("provenance", None)
                chunks.extend(
                    [
                        f"\n## {case.stem}\n",
                        full,
                        "\n### 全精度结果（SI 单位）\n",
                        "```json",
                        json.dumps(data, ensure_ascii=False, indent=2),
                        "```",
                    ]
                )
            except (ValueError, OSError, KeyError, TypeError, ArithmeticError, RuntimeError) as exc:
                failures.append(f"{case}: {exc}")
        (appendix / f"{chapter.name}_完整演算.md").write_text(
            "\n".join(chunks) + "\n", encoding="utf8"
        )
    if failures:
        raise SystemExit("\n".join(failures))
    print("全部书稿算例和逐章完整演算已生成。")


if __name__ == "__main__":
    main()
