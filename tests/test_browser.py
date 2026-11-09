"""浏览器入口与命令行复用同一计算内核。"""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from openresivent.browser import calculate_json
from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "case_file",
    [
        "cases/book/ch02/ex2-01.yaml",
        "cases/book/ch02/ex2-03.yaml",
        "cases/book/ch05/ex5-07.yaml",
        "cases/studies/makeup_base.yaml",
    ],
)
def test_browser_matches_cli(case_file, tmp_path):
    path = ROOT / case_file
    value = yaml.safe_load(path.read_text())
    result = CliRunner().invoke(app, ["run", str(path), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.exception
    native = json.loads((tmp_path / f"{value['meta']['id']}.json").read_text())
    browser = json.loads(calculate_json(json.dumps(value)))
    native.pop("provenance")
    browser.pop("provenance")
    assert native == browser


def test_browser_shaft_matches_cli(tmp_path):
    report = yaml.safe_load((ROOT / "cases/reports/shaft_example.yaml").read_text())
    value = {
        "meta": {"id": "shaft-test", "title": "竖井", "rules": []},
        "module": "shaft",
        "input": report["input"]["shaft"],
        "output": {},
    }
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(value))
    result = CliRunner().invoke(app, ["run", str(path), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.exception
    native = json.loads((tmp_path / "shaft-test.json").read_text())
    browser = json.loads(calculate_json(json.dumps(value)))
    native.pop("provenance")
    browser.pop("provenance")
    assert native == browser


def test_browser_rejects_unsupported():
    payload = {"meta": {"id": "sample", "title": "test"}, "module": "cfd_compare", "input": {}}
    with pytest.raises(ValueError, match="不支持"):
        calculate_json(json.dumps(payload))
