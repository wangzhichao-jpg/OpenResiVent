"""构建 onedir 测试目录并拒绝敏感内容，不生成安装包。"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prohibited(bundle: Path) -> list[str]:
    """扫描私有规则、书稿、气象文件和 ContamX；不依赖文件扩展名大小写。"""
    bad = []
    for path in bundle.rglob("*"):
        parts = [p.lower() for p in path.relative_to(bundle).parts]
        name = path.name.lower()
        if (
            ("private" in parts and "packs" in parts)
            or any(p in ("release_v1.0", "references", "contamx", "book") for p in parts)
            or name.endswith((".epw", ".ddy", ".stat"))
            or "contamx" in name
        ):
            bad.append(str(path.relative_to(bundle)))
    return bad


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=ROOT / "build/desktop-dist")
    args = parser.parse_args()
    web = ROOT / "build/web"
    if not (web / "index.html").is_file():
        raise SystemExit("请先构建前端")
    work = ROOT / "build/desktop-build"
    spec = ROOT / "build/desktop-spec"
    spec.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "resivent-desktop",
        "--distpath",
        str(args.dist),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
        "--paths",
        str(ROOT / "src"),
        "--collect-submodules",
        "openresivent",
        "--collect-data",
        "docx",
        "--exclude-module",
        "openresivent.rules.packs.private",
        "--exclude-module",
        "openresivent.network.contamx",
        "--exclude-module",
        "setuptools",
    ]
    pairs = [(web, "openresivent/web")]
    pairs.extend(
        (x, "openresivent/rules/packs")
        for x in sorted((ROOT / "src/openresivent/rules/packs").glob("*.yaml"))
    )
    pairs.extend((x, "openresivent/data") for x in sorted((ROOT / "data").glob("*.yaml")))
    for source, dest in pairs:
        cmd.extend(["--add-data", f"{source}{os.pathsep}{dest}"])
    cmd.append(str(ROOT / "packaging/desktop_entry.py"))
    subprocess.run(cmd, check=True, cwd=ROOT)
    # PyInstaller 将 Python 模块压进 PYZ，文件名扫描本身无法发现内部模块。
    from PyInstaller.archive.readers import ZlibArchiveReader

    archive = ZlibArchiveReader(str(work / "resivent-desktop" / "PYZ-00.pyz"))
    forbidden_modules = [
        name
        for name in archive.toc
        if "contamx" in name.lower() or name.startswith("openresivent.rules.packs.private")
    ]
    if forbidden_modules:
        raise SystemExit("模块归档包含禁止项：" + ", ".join(forbidden_modules))
    bundle = args.dist / "resivent-desktop"
    # python-docx 基于 parts/../templates 构造路径；即使模块在 PYZ，parts 目录也必须存在。
    parts = bundle / "_internal/docx/parts"
    parts.mkdir(parents=True, exist_ok=True)
    (parts / ".keep").write_text("用于定位文档模板。\n", encoding="utf8")
    bad = prohibited(bundle)
    if bad:
        raise SystemExit("打包内容包含禁止项：\n" + "\n".join(bad))
    size = sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file())
    print(f"打包检查通过：{bundle}，文件合计 {size} 字节；仅用于本机冒烟，不发布。")


if __name__ == "__main__":
    main()
