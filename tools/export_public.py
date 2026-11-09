"""按白名单原样复制本地公开快照；发现风险即报错，不自动转换。"""

import argparse
import shutil
from pathlib import Path

from scan_public import load_terms, scan

ROOT = Path(__file__).resolve().parents[1]
DIRS = (
    "src",
    "tests",
    "cases",
    "data",
    "web",
    "tools",
    "packaging",
    "docs/theory",
    "docs/verification",
    "docs/site",
    ".github/ISSUE_TEMPLATE",
    ".gitee/ISSUE_TEMPLATE",
)
FILES = (
    "README.md",
    "LICENSE",
    "NOTICE",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "THIRD_PARTY_NOTICES",
    "pyproject.toml",
    "mkdocs.yml",
    ".gitignore",
)
EXCLUDED_DIRS = {"node_modules", "build", ".venv", "__pycache__", ".git", "private"}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".epw",
    ".ddy",
    ".stat",
    ".prj",
    ".pdf",
    ".zip",
    ".exe",
    ".dll",
    ".so",
    ".whl",
    ".docx",
}
EXCLUDED_FILES = {
    "tools/inject_cases.py",
    "tests/test_inject_markers.py",
    "data/cfd_case_migration.json",
    "tools/migrate_cfd_cases.py",
    "tests/test_cfd_migration.py",
}


def allowed(relative: Path) -> bool:
    """拒绝外部文件、私有路径、缓存和本机生成物。"""
    low = str(relative).lower()
    return not (
        any(part.lower() in EXCLUDED_DIRS for part in relative.parts)
        or relative.suffix.lower() in EXCLUDED_SUFFIXES
        or "contamx" in low
        or str(relative) in EXCLUDED_FILES
        or relative.name in {".coverage", "book.lock"}
    )


def export(destination: Path) -> None:
    """向空目录逐字节复制允许的文件；风险扫描未通过时拒绝导出。"""
    terms = load_terms()
    if not terms:
        raise ValueError("未加载私有词表，禁止从开发库导出")
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents or destination in ROOT.parents:
        raise ValueError("目标不得为源仓库、其内部或父目录")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("目标目录必须为空")
    destination.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / file for file in FILES]
    for directory in DIRS:
        paths.extend((ROOT / directory).rglob("*"))
    for source in paths:
        relative = source.relative_to(ROOT)
        if not allowed(relative):
            continue
        if source.is_symlink():
            raise ValueError(f"源路径含符号链接: {relative}")
        if not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    findings = scan(destination, terms=terms)
    if findings:
        for path, line, category in findings:
            print(f"{path}:{line}: {category}")
        raise ValueError(f"导出检查发现 {len(findings)} 项，须直接修改源文件后重新导出")
    print("快照已写入", destination, "；未初始化仓库、未设置远程。")


def main() -> None:
    parser = argparse.ArgumentParser(description="向空目录原样导出可审查快照；不推送。")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export(args.destination)


if __name__ == "__main__":
    main()
