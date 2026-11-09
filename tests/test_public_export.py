"""公开导出和通用扫描回归。"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_scanner", ROOT / "tools/scan_public.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def test_scanner_general_and_private(tmp_path):
    book = tmp_path / "reference"
    book.mkdir()
    sample = "甲乙丙丁戊己庚辛壬癸" * 6
    (book / "chapter.md").write_text(sample, encoding="utf8")
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "private.txt").write_text("合成禁词", encoding="utf8")
    (root / "encoded.json").write_text(
        json.dumps({"x": "合成禁词"}, ensure_ascii=True), encoding="utf8"
    )
    (root / "encoded.py").write_text(
        "x = " + json.dumps("合成禁词", ensure_ascii=True), encoding="utf8"
    )
    (root / "email.txt").write_text("nobody" + chr(64) + "example.invalid", encoding="utf8")
    (root / "book.txt").write_text(sample[:50], encoding="utf8")
    terms = tmp_path / "terms.txt"
    terms.write_text("合成禁词\n", encoding="utf8")
    findings = scanner.scan(root, book, terms=scanner.load_terms(terms))
    assert {p for p, _, _ in findings} == {
        "private.txt",
        "encoded.json",
        "encoded.py",
        "email.txt",
        "book.txt",
    }
    assert not any(label == "私有词表命中" for _, _, label in scanner.scan(root, terms=()))
    assert scanner.load_terms(tmp_path / "missing") is None


def test_export_whitelist_and_clean_scan(tmp_path):
    if not scanner.load_terms():
        pytest.skip("公开快照未含私有词表，开发库导出需要词表")
    target = tmp_path / "public"
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/export_public.py"), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / "src/openresivent/cli.py").is_file()
    assert not (target / "tools/private").exists()
    assert not (target / "data/cfd_case_migration.json").exists()
    assert not (target / "tools/migrate_cfd_cases.py").exists()
    assert not (target / "tests/test_cfd_migration.py").exists()
    assert not (target / "docs/management").exists()
    assert not list(target.rglob("*.wasm"))
    assert not scanner.scan(target)
    for path in target.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (ROOT / path.relative_to(target)).read_bytes()


def test_optional_private_file_auto_load(tmp_path, monkeypatch):
    terms = tmp_path / "terms.txt"
    terms.write_text("合成禁词\n", encoding="utf8")
    monkeypatch.setattr(scanner, "PRIVATE_TERMS", terms)
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "sample.txt").write_text("合成禁词", encoding="utf8")
    assert any(label == "私有词表命中" for _, _, label in scanner.scan(root))


def test_missing_private_fails_export(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("exporter", ROOT / "tools/export_public.py")
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exporter)
        monkeypatch.setattr(exporter, "load_terms", lambda: None)
        with pytest.raises(ValueError, match="未加载私有词表"):
            exporter.export(tmp_path / "out")
    finally:
        sys.path.pop(0)


def test_license_email_exception_is_exact(tmp_path):
    source = ROOT / "web/licenses/zlib-1.2.13.txt"
    target = tmp_path / "web/licenses/zlib-1.2.13.txt"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    assert not scanner.scan(tmp_path, terms=())
    target.write_bytes(target.read_bytes() + b" ")
    assert any(label == "邮箱" for _, _, label in scanner.scan(tmp_path, terms=()))


def test_scanner_rejects_binary_and_symlink(tmp_path):
    (tmp_path / "bytes.unknown").write_bytes(b"\xff\x00")
    try:
        (tmp_path / "link").symlink_to(tmp_path / "bytes.unknown")
    except OSError:
        pytest.skip("平台不支持符号链接")
    labels = {label for _, _, label in scanner.scan(tmp_path, terms=())}
    assert {"非 UTF-8 或二进制文件", "符号链接"} <= labels
