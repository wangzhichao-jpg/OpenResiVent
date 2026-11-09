"""运行时准备的预览、重试和完整性检查。"""

import hashlib
import importlib.util
import io
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "runtime_prepare", ROOT / "tools/prepare_browser_runtime.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_help_and_preview_do_not_download(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(module, "OUT", tmp_path / "out")
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: pytest.fail("不得下载"))
    monkeypatch.setattr(sys, "argv", ["prepare", "--help"])
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 0
    monkeypatch.setattr(sys, "argv", ["prepare", "--dry-run"])
    module.main()
    assert not module.OUT.exists()
    assert "仅预览" in capsys.readouterr().out


def test_source_archive_reproducible_across_file_times(tmp_path):
    import os

    root = tmp_path / "source"
    source = root / "src/openresivent/module.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n")
    one, two = tmp_path / "one.zip", tmp_path / "two.zip"
    os.utime(source, (1000000000, 1000000000))
    module.write_source_archive(root, one)
    os.utime(source, (1500000000, 1500000000))
    module.write_source_archive(root, two)
    assert one.read_bytes() == two.read_bytes()


def test_preview_without_installed_runtime(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(module, "NPM", tmp_path / "missing")
    monkeypatch.setattr(module, "OUT", tmp_path / "out")
    monkeypatch.setattr(sys, "argv", ["prepare", "--dry-run"])
    module.main()
    assert "尚未安装" in capsys.readouterr().out
    assert not module.OUT.exists()


def test_retry_checks_hash_each_time(tmp_path, monkeypatch):
    responses = iter([URLError("temporary"), b"bad", b"valid"])
    calls = []

    def open_url(*args, **kwargs):
        calls.append(args)
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(value)

    monkeypatch.setattr(module.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    target = tmp_path / "file"
    module.download("https://example.test/file", target, hashlib.sha256(b"valid").hexdigest())
    assert len(calls) == 3 and target.read_bytes() == b"valid"
    assert not target.with_suffix(".part").exists()


def test_failed_hash_does_not_replace_existing(tmp_path, monkeypatch):
    target = tmp_path / "file"
    target.write_bytes(b"previous")
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"bad"))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    with pytest.raises(ValueError, match="SHA256"):
        module.download("https://example.test/file", target, hashlib.sha256(b"valid").hexdigest())
    assert target.read_bytes() == b"previous"
    assert not target.with_suffix(".part").exists()


def test_help_subprocess():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/prepare_browser_runtime.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and "--dry-run" in result.stdout
