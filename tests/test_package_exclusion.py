"""构建钩子及候选发布档案的浏览器运行时排除。"""

import importlib.util
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("orv_hatch_hook", ROOT / "packaging/hatch_build.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_hook_excludes_runtime_and_sdist_assets(tmp_path):
    web = tmp_path / "build/web"
    (web / "pyodide").mkdir(parents=True)
    (web / "index.html").write_text("service")
    (web / "bundle.js").write_text("service")
    (web / "pyodide/engine.wasm").write_bytes(b"runtime")
    (web / "hidden.wasm").write_bytes(b"runtime")
    result = {}
    hook = module.CustomBuildHook(str(tmp_path), {}, None, None, "", "wheel")
    hook.initialize("test", result)
    assert set(result["force_include"].values()) == {
        "openresivent/web/index.html",
        "openresivent/web/bundle.js",
    }
    result = {}
    module.CustomBuildHook(str(tmp_path), {}, None, None, "", "sdist").initialize("test", result)
    assert not result


def test_release_archives_exclude_browser_runtime():
    archive_dir = os.environ.get("ORV_ARCHIVE_DIR")
    if not archive_dir:
        pytest.skip("未指定待检查的发布档案目录")
    root = Path(archive_dir)
    wheels, sdists = list(root.glob("*.whl")), list(root.glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_names = wheel.namelist()
    with tarfile.open(sdists[0]) as sdist:
        source_names = sdist.getnames()
    for name in wheel_names + source_names:
        assert "pyodide" not in name.lower() and not name.lower().endswith(".wasm"), name
    assert any(name.endswith("openresivent/web/index.html") for name in wheel_names)
    assert not any("/build/web/" in name for name in source_names)
