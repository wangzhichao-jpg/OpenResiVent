"""公开快照扫描器：已审核图片资源的精确放行行为测试。"""

import hashlib
import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = PROJECT_ROOT / "tools" / "scan_public.py"
APPROVED_REL = "docs/images/household_check.png"
APPROVED_SOURCE = PROJECT_ROOT / APPROVED_REL
FAKE_TERM = "仅用于测试的私有词"
FAKE_TOKEN = "sk" + "-" + "TEST" * 6


def load_scanner():
    spec = importlib.util.spec_from_file_location("scan_public_under_test", SCANNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scanner():
    module = load_scanner()
    assert module.APPROVED_BINARY_ASSETS.get(APPROVED_REL)
    return module


@pytest.fixture()
def approved_bytes():
    return APPROVED_SOURCE.read_bytes()


def write(root, rel, data):
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def labels(issues, rel):
    return [label for path, _line, label in issues if path == rel]


def test_constant_matches_real_asset(scanner, approved_bytes):
    expected = hashlib.sha256(approved_bytes).hexdigest()
    assert scanner.APPROVED_BINARY_ASSETS[APPROVED_REL] == expected
    assert approved_bytes.startswith(scanner.PNG_SIGNATURE)


def test_approved_asset_passes(scanner, tmp_path, approved_bytes):
    write(tmp_path, APPROVED_REL, approved_bytes)
    assert scanner.scan(tmp_path) == []


def test_modified_byte_fails(scanner, tmp_path, approved_bytes):
    data = bytearray(approved_bytes)
    data[-1] = data[-1] ^ 0xFF
    write(tmp_path, APPROVED_REL, bytes(data))
    assert labels(scanner.scan(tmp_path), APPROVED_REL) == ["审核图片完整性失败"]


def test_fake_png_at_approved_path_fails(scanner, tmp_path):
    write(tmp_path, APPROVED_REL, scanner.PNG_SIGNATURE + b"not-the-approved-image")
    assert labels(scanner.scan(tmp_path), APPROVED_REL) == ["审核图片完整性失败"]


def test_fake_png_elsewhere_fails(scanner, tmp_path):
    rel = "docs/images/other.png"
    write(tmp_path, rel, scanner.PNG_SIGNATURE + b"\xff\xfe\x00\x01")
    assert labels(scanner.scan(tmp_path), rel)


def test_real_png_at_other_path_fails(scanner, tmp_path, approved_bytes):
    rel = "docs/images/copied.png"
    write(tmp_path, rel, approved_bytes)
    found = labels(scanner.scan(tmp_path), rel)
    assert found
    assert "审核图片完整性失败" not in found


def test_symlink_is_rejected(scanner, tmp_path, approved_bytes):
    real = write(tmp_path, "docs/images/real_source.png", approved_bytes)
    link = tmp_path / APPROVED_REL
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(real)
    assert "符号链接" in labels(scanner.scan(tmp_path), APPROVED_REL)


def test_private_term_and_fake_credential_detected(scanner, tmp_path):
    rel = "notes/release.md"
    write(tmp_path, rel, f"包含 {FAKE_TERM} 与凭据 {FAKE_TOKEN}\n".encode())
    found = labels(scanner.scan(tmp_path, terms=(FAKE_TERM,)), rel)
    assert "私有词表命中" in found
    assert "凭据" in found
