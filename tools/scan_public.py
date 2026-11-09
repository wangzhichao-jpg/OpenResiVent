"""公开快照的本地敏感内容扫描。"""

import argparse
import re
from pathlib import Path

# 不在源码中直接写入被检索的词，以免扫描器命中自身。
TERMS = tuple(
    bytes.fromhex(value).decode("utf8")
    for value in (
        "e5b7a5e4bd9ce68c87e4bba4",
        "574f2d50",
        "4d53472d",
        "e7aea1e79086e7abaf",
        "e696bde5b7a5e7abaf",
        "e9aa8ce694b6e696b9",
        "e4bfaee8aea2e88d89e6a188",
        "e5be81e6b182e6848fe8a781e7a8bf",
        "e98081e5aea1e7a8bf",
        "e68aa5e689b9e7a8bf",
        "e7bc96e588b6e5a4a7e7bab2",
        "e4bfaee8aea2e6b885e58d95",
        "e7a094e7a9b6e8afbee9a298",
        "e590afe58aa8e4bc9a",
        "e4bfaee8aea2e7bc96e588b6",
    )
)
BRANDS = tuple(
    bytes.fromhex(value).decode("utf8")
    for value in (
        "e5a4a7e98791",
        "e99c8de5b0bce99fa6e5b094",
        "e69dbee4b88b",
        "e7be8ee79a84",
        "e6b5b7e5b094",
    )
)
PATTERNS = {
    "本机绝对路径": re.compile(
        r'/(?:home|Users)/[A-Za-z0-9_.-]+/[^\s"\']+|[A-Za-z]:\\Users\\[^\s"\']+'
    ),
    "会话标识": re.compile(
        r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
    ),
    "邮箱": re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b"),
    "凭据": re.compile(
        r'(?i)(?:sk|ghp|github_pat|gitee|xoxb)[-_][A-Za-z0-9_-]{16,}|(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*["\'][A-Za-z0-9_./+-]{12,}["\']'
    ),
}
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def book_windows(book):
    """生成正文去空白后 50 字滑窗；不输出书稿内容。"""
    result = set()
    for path in sorted(book.glob("*.md")):
        text = re.sub(r"\s+", "", path.read_text(encoding="utf8"))
        result.update(text[i : i + 50] for i in range(max(0, len(text) - 49)))
    return result


def scan(root, book=None):
    """返回 (相对路径,行号,类别)；不打印命中内容。"""
    windows = book_windows(book) if book and book.is_dir() else set()
    issues = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.is_symlink():
            issues.append((str(rel), 0, "符号链接"))
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf8")
        except UnicodeError:
            issues.append((str(rel), 0, "非 UTF-8 或二进制文件"))
            continue
        if "\x00" in text:
            issues.append((str(rel), 0, "二进制文件"))
            continue
        for no, line in enumerate(text.splitlines(), 1):
            for term in TERMS + BRANDS:
                if term.lower() in line.lower():
                    issues.append((str(rel), no, "敏感词"))
                    break
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    issues.append((str(rel), no, label))
        if windows:
            compact = re.sub(r"\s+", "", text)
            if any(compact[i : i + 50] in windows for i in range(max(0, len(compact) - 49))):
                issues.append((str(rel), 0, "正文连续片段"))
    return issues


def main():
    parser = argparse.ArgumentParser(description="扫描导出快照；发现问题返回非零。")
    parser.add_argument("root", type=Path)
    parser.add_argument("--book", type=Path, help="可选的正文目录；仅在本地比对，不输出内容")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error("扫描目录不存在")
    if args.book and not args.book.is_dir():
        parser.error("正文目录不存在")
    issues = scan(args.root.resolve(), args.book)
    for path, line, label in issues:
        print(f"{path}:{line}: {label}")
    print(f"共 {len(issues)} 项；正文比对：{'已执行' if args.book else '未提供正文'}")
    raise SystemExit(bool(issues))


if __name__ == "__main__":
    main()
