"""检验普通安装后的静态资源，不以源码导入替代安装。"""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openresivent.api import app

ROOT = Path(__file__).resolve().parents[1]


def test_web_override_and_fallback(monkeypatch, tmp_path):
    from openresivent import api

    (tmp_path / "index.html").write_text("覆盖页面", encoding="utf8")
    monkeypatch.setenv("ORV_WEB_DIR", str(tmp_path))
    assert TestClient(app).get("/").text == "覆盖页面"
    # 模拟安装位置和源码布局均无资源。
    monkeypatch.delenv("ORV_WEB_DIR")
    monkeypatch.setattr(
        api, "__file__", str(tmp_path / "fake" / "site-packages" / "openresivent" / "api.py")
    )
    r = TestClient(app).get("/")
    assert r.status_code == 200 and "界面尚未构建" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert TestClient(app).get("/absent.js").status_code == 404


def test_regular_install_and_serve(tmp_path):
    if not (ROOT / "build/web/index.html").is_file():
        pytest.skip("需先构建前端")
    envdir = tmp_path / "env"
    subprocess.run([sys.executable, "-m", "venv", str(envdir)], check=True)
    python = envdir / "bin/python"
    env = os.environ.copy()
    env.pop("ORV_WEB_DIR", None)
    # 构建器及运行依赖来自测试环境；项目包必须从独立安装目录导入。
    env["PYTHONPATH"] = str(
        Path(sys.executable).absolute().parents[1]
        / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    )
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", "--no-build-isolation", str(ROOT)],
        check=True,
        capture_output=True,
        env=env,
        cwd=tmp_path,
    )
    package = subprocess.check_output(
        [str(python), "-c", "import openresivent;print(openresivent.__file__)"],
        cwd=tmp_path,
        env=env,
        text=True,
    ).strip()
    assert str(envdir) in package
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [
            str(envdir / "bin/resivent"),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as r:
                    html = r.read().decode()
                    csp = r.headers["Content-Security-Policy"]
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.1)
        else:
            pytest.fail("已安装服务未启动")
        assert '<div id="app">' in html and "default-src 'self'" in csp
        assert "界面尚未构建" not in html
    finally:
        p.terminate()
        p.wait(timeout=10)
