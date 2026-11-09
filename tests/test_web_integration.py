"""浏览器映射使用的三个示例与 API、命令行的一致性。"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from openresivent.api import app
from openresivent.cli import app as cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "path,kind",
    [
        ("cases/book/ch02/ex2-03.yaml", "ventilation"),
        ("cases/book/ch05/ex5-07.yaml", "dwelling"),
        ("cases/reports/shaft_example.yaml", "shaft"),
    ],
)
def test_cases_api_cli(tmp_path, path, kind):
    binary = ROOT / "web/node_modules/.bin/vite-node"
    if not binary.is_file():
        pytest.skip("未安装前端依赖，跳过前端映射集成测试")
    mapped = subprocess.run(
        [str(binary), "src/export-fixtures.js"],
        cwd=ROOT / "web",
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(mapped.stdout)[kind]
    original = yaml.safe_load((ROOT / path).read_text())
    if kind == "shaft":
        assert payload["input"] == original["input"]["shaft"]
    else:
        assert payload == original
    source = tmp_path / "case.yaml"
    source.write_text(yaml.safe_dump(payload, allow_unicode=True))
    response = TestClient(app).post("/run", json=payload)
    assert response.status_code == 200, response.text
    result = CliRunner().invoke(cli, ["run", str(source), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.exception
    cli_data = json.loads((tmp_path / f"{payload['meta']['id']}.json").read_text())
    a = response.json()
    a.pop("provenance")
    cli_data.pop("provenance")
    assert a == cli_data
