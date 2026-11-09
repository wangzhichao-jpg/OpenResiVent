"""公开快照隔离及扫描器敏感样例回归。"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_scanner", ROOT / "tools/scan_public.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def test_scanner_detects_each_category(tmp_path):
    scan = tmp_path / "snapshot"
    scan.mkdir()
    book = tmp_path / "reference"
    book.mkdir()
    sample = "甲乙丙丁戊己庚辛壬癸" * 6
    (book / "chapter.md").write_text(sample, encoding="utf8")
    samples = {
        "term": scanner.TERMS[0],
        "brand": scanner.BRANDS[0],
        "unix": "/" + "home/" + "someone/private.txt",
        "windows": "C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "private.txt",
        "uuid": "12345678" + "-1234-4abc-8abc-" + "123456789012",
        "email": "person" + chr(64) + "example.invalid",
        "secret": "sk-" + "a" * 32,
        "excerpt": sample[:50],
    }
    for name, value in samples.items():
        (scan / (name + ".txt")).write_text(value, encoding="utf8")
    findings = scanner.scan(scan, book)
    assert {Path(path).stem for path, _, _ in findings} == set(samples)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/scan_public.py"), str(scan), "--book", str(book)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert sample not in result.stdout


def test_export_whitelist_and_clean_scan(tmp_path):
    target = tmp_path / "public"
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/export_public.py"), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "src/openresivent/cli.py").is_file()
    assert not (target / "docs/management").exists()
    assert not (target / "docs/decisions").exists()
    assert not (target / "AGENTS.md").exists()
    assert not list(target.rglob("*.prj"))
    assert not any("contamx" in p.name.lower() for p in target.rglob("*"))
    assert not scanner.scan(target)
    again = subprocess.run(
        [sys.executable, str(ROOT / "tools/export_public.py"), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert again.returncode != 0
    assert not (target / ".git").exists()


def test_scanner_rejects_binary_and_symlink(tmp_path):
    (tmp_path / "bytes.unknown").write_bytes(b"\xff\x00")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "hidden.txt").write_text(scanner.TERMS[0], encoding="utf8")
    try:
        (tmp_path / "link").symlink_to(tmp_path / "bytes.unknown")
    except OSError:
        pytest.skip("平台不支持符号链接")
    labels = {label for _, _, label in scanner.scan(tmp_path)}
    assert {"非 UTF-8 或二进制文件", "符号链接", "敏感词"} <= labels
