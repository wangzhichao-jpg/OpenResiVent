"""根据 npm 锁文件生成前端依赖许可清单；不访问网络。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    """读取锁文件并导出每个依赖的名称、版本及许可。"""
    lock = json.loads((ROOT / "web/package-lock.json").read_text())
    rows = []
    allowed = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "0BSD", "MPL-2.0"}
    for path, item in sorted(lock["packages"].items()):
        if not path:
            continue
        license = item.get("license")
        if license not in allowed:
            raise ValueError(f"待核许可：{path} {license}")
        rows.append(f"| {path.removeprefix('node_modules/')} | {item['version']} | {license} |")
    text = (
        "# 前端依赖许可清单\n\n由 `web/package-lock.json` 元数据生成；依赖的许可证全文在安装后的各包目录，分发构建产物前仍应核查并附带相关声明。\n\n| 包 | 版本 | 许可 |\n|---|---|---|\n"
        + "\n".join(rows)
        + "\n"
    )
    (ROOT / "docs/frontend-licenses.md").write_text(text, encoding="utf8")


if __name__ == "__main__":
    main()
