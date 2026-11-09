"""桌面回退、回环绑定和包内容红线。"""

import importlib.util
import sys
import time
from pathlib import Path

from typer.testing import CliRunner

from openresivent import desktop as desktop_module
from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[1]


def test_fallback_browser_and_loopback(monkeypatch):
    calls = {}

    class Config:
        def __init__(self, app, **kwargs):
            calls["config"] = kwargs

    class Server:
        def __init__(self, config):
            self.started = False
            self.should_exit = False
            calls["server"] = self

        def run(self, sockets):
            calls["address"] = sockets[0].getsockname()
            self.started = True
            while not self.should_exit:
                time.sleep(0.001)

    monkeypatch.setattr(desktop_module.uvicorn, "Config", Config)
    monkeypatch.setattr(desktop_module.uvicorn, "Server", Server)
    monkeypatch.setitem(sys.modules, "webview", None)

    def opened(url):
        calls["url"] = url
        calls["server"].should_exit = True
        return True

    monkeypatch.setattr(desktop_module.webbrowser, "open", opened)
    desktop_module.desktop()
    assert calls["address"][0] == "127.0.0.1" and calls["address"][1] > 0
    assert calls["url"] == f"http://127.0.0.1:{calls['address'][1]}/"
    assert calls["config"]["host"] == "127.0.0.1"


def test_cli_desktop_invokes_launcher(monkeypatch):
    invoked = []
    monkeypatch.setattr(desktop_module, "desktop", lambda: invoked.append(True))
    result = CliRunner().invoke(app, ["desktop"])
    assert result.exit_code == 0 and invoked == [True]


def test_exclusion_scan(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "build_desktop", ROOT / "packaging/build_desktop.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "_internal/openresivent/rules/packs/private").mkdir(parents=True)
    (tmp_path / "beijing.epw").write_text("not weather")
    assert len(module.prohibited(tmp_path)) >= 2
