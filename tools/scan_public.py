"""公开快照的通用检查与可选本地词表扫描。"""

import argparse
import hashlib
import re
from pathlib import Path

PRIVATE_TERMS = Path(__file__).resolve().parent / "private/scan_terms.txt"
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
# 上游许可原文按路径、哈希和地址精确放行；合成测试按文件和完整行精确放行。
LICENSE_EMAIL_ALLOWLIST = {
    (
        "web/licenses/zlib-1.2.13.txt",
        "845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243",
        "jloup@gzip.org",
    ),
    (
        "web/licenses/zlib-1.2.13.txt",
        "845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243",
        "madler@alumni.caltech.edu",
    ),
    (
        "web/licenses/bzip2-1.0.6.txt",
        "4919cfb14a73cd64fcef67b107613970cf1659a09aa675dba31314f373bc7204",
        "jseward@bzip.org",
    ),
}
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}

# 已审核的图片资源只按“精确相对路径 + 固定 SHA256 + PNG 签名”放行，不按扩展名放行任何二进制。
APPROVED_BINARY_ASSETS = {
    "docs/images/household_check.png": "280184377e6b30faac617f44415c8744fe37fa372f1c918897b57ef1849ed2ce",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def load_terms(path=None):
    """返回词表；缺失时返回 None，空词表无效。"""
    path = Path(path) if path is not None else PRIVATE_TERMS
    if not path.is_file():
        return None
    terms = tuple(
        x.strip()
        for x in path.read_text(encoding="utf8").splitlines()
        if x.strip() and not x.lstrip().startswith("#")
    )
    if not terms:
        raise ValueError("私有词表为空")
    return terms


def book_windows(book):
    result = set()
    for path in sorted(book.glob("*.md")):
        text = re.sub(r"\s+", "", path.read_text(encoding="utf8"))
        result.update(text[i : i + 50] for i in range(max(0, len(text) - 49)))
    return result


def decode_escapes(line):
    """解码 Unicode 单元，不破坏原有中文。"""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), line)


def scan(root, book=None, terms=None):
    """返回路径、行号和类别；可显式传入词表，缺省自动读取。"""
    if terms is None:
        terms = load_terms() or ()
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
        approved_sha = APPROVED_BINARY_ASSETS.get(rel.as_posix())
        if approved_sha is not None:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != approved_sha or not raw.startswith(PNG_SIGNATURE):
                issues.append((str(rel), 0, "审核图片完整性失败"))
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf8")
        except UnicodeError:
            issues.append((str(rel), 0, "非 UTF-8 或二进制文件"))
            continue
        if "\x00" in text:
            issues.append((str(rel), 0, "二进制文件"))
            continue
        digest = hashlib.sha256(raw).hexdigest()
        for no, original in enumerate(text.splitlines(), 1):
            line = decode_escapes(original) if path.suffix in (".json", ".py") else original
            if any(term.casefold() in line.casefold() for term in terms):
                issues.append((str(rel), no, "私有词表命中"))
            for label, pattern in PATTERNS.items():
                matches = list(pattern.finditer(line))
                if label == "邮箱":
                    matches = [
                        m
                        for m in matches
                        if (rel.as_posix(), digest, m.group()) not in LICENSE_EMAIL_ALLOWLIST
                        and not (
                            rel.as_posix() == "tools/scan_public.py"
                            and original.strip() == f'"{m.group()}",'
                            and any(m.group() == entry[2] for entry in LICENSE_EMAIL_ALLOWLIST)
                        )
                    ]
                if matches:
                    issues.append((str(rel), no, label))
        if windows:
            compact = re.sub(r"\s+", "", text)
            if any(compact[i : i + 50] in windows for i in range(max(0, len(compact) - 49))):
                issues.append((str(rel), 0, "正文连续片段"))
    return issues


def main():
    parser = argparse.ArgumentParser(description="扫描导出快照；发现问题返回非零。")
    parser.add_argument("root", type=Path)
    parser.add_argument("--book", type=Path)
    args = parser.parse_args()
    if not args.root.is_dir() or (args.book and not args.book.is_dir()):
        parser.error("扫描目录或正文目录不存在")
    terms = load_terms()
    print("已加载私有词表" if terms else "未加载私有词表")
    issues = scan(args.root.resolve(), args.book, terms=terms or ())
    for path, line, label in issues:
        print(f"{path}:{line}: {label}")
    print(f"共 {len(issues)} 项；正文比对：{'已执行' if args.book else '未提供正文'}")
    raise SystemExit(bool(issues))


if __name__ == "__main__":
    main()
