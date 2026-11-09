"""前端扫描映射经本机 API 与命令行端到端一致。"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from openresivent.api import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("kind", ["shaft", "makeup"])
def test_frontend_api_cli_sweep(tmp_path, monkeypatch, kind):
    binary = ROOT / "web/node_modules/.bin/vite-node"
    if not binary.is_file():
        pytest.skip("未安装前端依赖")
    mapped = subprocess.run(
        [str(binary), "src/export-sweep.js"],
        cwd=ROOT / "web",
        capture_output=True,
        text=True,
        check=True,
    )
    item = json.loads(mapped.stdout)[kind]
    root = tmp_path / "sweep-root"
    monkeypatch.setenv("ORV_SWEEP_DIR", str(root))
    client = TestClient(app)
    response = client.post("/sweep", json={**item, "out": "web", "workers": 1})
    assert response.status_code == 202, response.text
    job = response.json()["job_id"]
    for _ in range(600):
        status = client.get("/sweep/" + job).json()
        if status["status"] != "running":
            break
        time.sleep(0.05)
    assert status["status"] == "completed", status
    spec = item["spec"]
    (tmp_path / spec["base_case"]).write_text(yaml.safe_dump(item["case"], allow_unicode=True))
    path = tmp_path / "sweep.yaml"
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "openresivent.cli",
            "sweep",
            str(path),
            "--out",
            str(tmp_path / "cli"),
            "--workers",
            "1",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=45,
    )
    assert (
        client.get(f"/sweep/{job}/files/samples.csv").content
        == (tmp_path / "cli/samples.csv").read_bytes()
    )
    assert (root / "web/statistics.json").read_bytes() == (
        tmp_path / "cli/statistics.json"
    ).read_bytes()
