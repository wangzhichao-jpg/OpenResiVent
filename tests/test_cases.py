"""算例分派与书稿锁验收。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("path", ["ch01/ex1-01.yaml", "ch02/ex2-03.yaml", "ch06/ex6-01.yaml"])
def test_dispatch(path, tmp_path):
    result = CliRunner().invoke(
        app, ["run", str(ROOT / "cases/book" / path), "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.exception
    payload = json.loads((tmp_path / (Path(path).stem + ".json")).read_text())
    assert len(payload["provenance"]["input_sha256"]) == 64
    if "design" in payload:
        assert payload["checks"] and all(x["passed"] for x in payload["checks"])
        assert payload["international"]["ashrae_m3_s"] == pytest.approx(0.0275)
    else:
        ci = payload["points"]["point_1"]["ci95"]
        assert ci[0] < 0.8 / 3600 < ci[1]


def test_lock_detects_changed_input(tmp_path):
    if not (ROOT / "external-book-not-provided/ch02.md").exists() and not os.environ.get(
        "ORV_BOOK_DIR"
    ):
        pytest.skip("未提供书稿；设置 ORV_BOOK_DIR 可运行嵌入测试")
    import importlib.util

    spec = importlib.util.spec_from_file_location("inject", ROOT / "tools/inject_cases.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CASE = tmp_path / "case.yaml"
    module.CASE.write_bytes((ROOT / "cases/book/ch02/ex2-01.yaml").read_bytes())
    module.OUT = tmp_path / "out"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    # 替换子进程调用，仍在独立进程运行真实 CLI。
    original = subprocess.run
    module.subprocess.run = lambda args, **kw: original(args, env=env, **kw)
    old = sys.argv
    try:
        sys.argv = ["inject"]
        assert module.main() == 0
        assert module.main() == 0
        module.CASE.write_text(module.CASE.read_text().replace("occupants: 3", "occupants: 4"))
        assert module.main() == 1
    finally:
        sys.argv = old
        module.subprocess.run = original
