"""一户校核与原模块、API、命令行和文档的一致性。"""

import io
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from docx import Document
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from openresivent import __version__
from openresivent.api import app
from openresivent.cli import app as cli
from openresivent.core.case import Case
from openresivent.core.runner import execute
from openresivent.household_check import HouseholdCheck, calculate
from openresivent.report.docx_report import document_text

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_matches_modules_api_cli(tmp_path):
    source = ROOT / "cases/workflows/household_example.yaml"
    raw = yaml.safe_load(source.read_text())
    data = HouseholdCheck.model_validate(raw)
    result = calculate(data)
    assert result["ventilation"] == execute(data.ventilation, source)[0]
    assert result["dwelling"] == execute(data.dwelling, source)[0]
    home = data.dwelling.input
    for n in home["n50_per_h"]:
        case = Case.model_validate(
            {
                "meta": {"id": "inverse", "title": "补风", "rules": []},
                "module": "makeup_design",
                "input": {
                    "bedrooms": home["bedrooms"],
                    "volume_m3": home["volume_m3"],
                    "n50_per_h": n,
                    "hood_m3_h": home["hood_m3_h"],
                    "fresh_supply_m3_h": home["fresh_supply_m3_h"],
                    "fresh_exhaust_m3_h": home["fresh_exhaust_m3_h"],
                    "threshold_pa": home["threshold_pa"],
                },
            }
        )
        assert result["inverse"][str(n)] == execute(case, source)[0]
    response = TestClient(app).post("/household-check", json=raw)
    assert response.status_code == 200, response.text
    assert response.json() == result
    command = CliRunner().invoke(cli, ["check", str(source), "--out", str(tmp_path)])
    assert command.exit_code == 0, command.exception
    assert json.loads((tmp_path / "result.json").read_text()) == result
    document = Document(tmp_path / "report.docx")
    text = document_text(document)
    assert __version__ in text and "来源分级" in text and "条文校核汇总" in text
    assert f"{result['ventilation']['design'] * 3600:.1f}" in text
    assert f"{result['inverse']['1.0']['mechanical']['value'] * 3600:.1f}" in text
    assert f"{result['inverse']['1.0']['opening']['value'] * 10000:.0f}" in text
    assert (
        f"{result['dwelling']['scenarios']['1.0']['no_makeup']['pressures_pa']['kitchen']:.1f}"
        in text
    )
    assert "GB/T 18883-2022 第4.2条、表1" in text
    assert "示例值，需用户确认" in text
    assert not re.search(
        r"bedrooms\[|scenarios\.|pressures_pa|area_m2|\b\d+(?:\.\d+)?[eE][+-]\d+\b", text
    )
    assert "15 Pa 为示例提示值，不是燃气安全限值" in text
    assert "-0.0" not in text
    assert all(f"卧室{i}：" in text for i in range(1, 4))
    input_rows = [[cell.text for cell in row.cells] for row in document.tables[0].rows]
    assert next(row for row in input_rows if row[0] == "空气密度")[-1] == "通用参数"
    tables = [
        [[cell.text for cell in row.cells] for row in table.rows] for table in document.tables
    ]
    flow_table = next(table for table in tables if table[0][0:2] == ["房间", "换气次数法 m³/h"])
    for i, bedroom in enumerate(result["ventilation"]["bedrooms"], 1):
        row = flow_table[i]
        assert row[0] == f"卧室{i}"
        assert row[1:5] == [
            f"{bedroom[key] * 3600:.1f}" if bedroom.get(key) is not None else "未启用"
            for key in ("A", "B", "C", "D")
        ]
        assert row[5] == f"{bedroom['selected'] * 3600:.1f}"
    summary = next(table for table in tables if table[0][:2] == ["气密性 次/h", "补风方案"])
    assert (
        summary[1][2]
        == f"{result['dwelling']['scenarios']['1.0']['no_makeup']['pressures_pa']['kitchen']:.1f}"
    )
    assert summary[1][4] == "警示：超过提示值"
    inverse = next(table for table in tables if table[0][1] == "最小机械补风 m³/h")
    assert inverse[1][1:] == [
        f"{result['inverse']['1.0']['mechanical']['value'] * 3600:.1f}",
        f"{result['inverse']['1.0']['opening']['value'] * 10000:.0f}",
    ]
    downloaded = TestClient(app).post("/household-check/report", json=raw)
    assert downloaded.status_code == 200
    assert __version__ in document_text(Document(io.BytesIO(downloaded.content)))


def test_frontend_generated_file_api_cli(tmp_path):
    binary = ROOT / "web/node_modules/.bin/vite-node"
    if not binary.is_file():
        pytest.skip("未安装前端依赖")
    mapped = subprocess.run(
        [str(binary), "src/export-household.js"],
        cwd=ROOT / "web",
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(mapped.stdout)
    path = tmp_path / "household.json"
    path.write_text(mapped.stdout, encoding="utf8")
    response = TestClient(app).post("/household-check", json=payload)
    assert response.status_code == 200, response.text
    command = CliRunner().invoke(cli, ["check", str(path), "--out", str(tmp_path / "out")])
    assert command.exit_code == 0, command.exception
    actual = json.loads((tmp_path / "out/result.json").read_text())
    assert response.json() == actual
    assert (
        actual["ventilation"]
        == execute(HouseholdCheck.model_validate(payload).ventilation, path)[0]
    )
    assert actual["dwelling"] == execute(HouseholdCheck.model_validate(payload).dwelling, path)[0]


def test_workflow_with_noise(tmp_path):
    raw = yaml.safe_load((ROOT / "cases/workflows/household_example.yaml").read_text())
    noise = yaml.safe_load((ROOT / "cases/book/ch04/ex4-09.yaml").read_text())["input"]
    raw["ventilation"]["input"]["noise"] = noise
    path = tmp_path / "input.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True))
    response = TestClient(app).post("/household-check", json=raw)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["ventilation"]["noise"]["settings"]) == 3
    command = CliRunner().invoke(cli, ["check", str(path), "--out", str(tmp_path / "output")])
    assert command.exit_code == 0, command.exception
    assert json.loads((tmp_path / "output/result.json").read_text()) == result
    text = document_text(Document(tmp_path / "output/report.docx"))
    assert f"{result['ventilation']['noise']['settings'][0]['a_weighted_db']:.1f}" in text


def test_source_classification_user_and_standard(tmp_path):
    raw = yaml.safe_load((ROOT / "cases/workflows/household_example.yaml").read_text())
    raw["sources"]["ventrate.area_m2"] = "用户输入"
    raw["sources"]["ventrate.limit_ppm"] = "用户输入"
    data = HouseholdCheck.model_validate(raw)
    from openresivent.household_check import save_report

    path = save_report(data, calculate(data), tmp_path / "report.docx")
    tables = Document(path).tables
    rows = [[cell.text for cell in row.cells] for row in tables[0].rows]
    assert next(row for row in rows if row[0] == "居住面积")[-1] == "用户输入"
    assert next(row for row in rows if row[0] == "室内二氧化碳浓度限值")[-1] == "用户输入"
    assert next(row for row in rows if row[0] == "设计人数")[-1] == "示例值，需用户确认"
    raw["sources"].pop("ventrate.limit_ppm")
    raw["ventilation"]["input"]["limit_ppm"] = 1200
    data = HouseholdCheck.model_validate(raw)
    path = save_report(data, calculate(data), tmp_path / "modified.docx")
    rows = [[cell.text for cell in row.cells] for row in Document(path).tables[0].rows]
    assert next(row for row in rows if row[0] == "室内二氧化碳浓度限值")[-1] == "示例值，需用户确认"
    del raw["ventilation"]["input"]["limit_ppm"]
    raw["ventilation"]["meta"]["rules"] = []
    data = HouseholdCheck.model_validate(raw)
    path = save_report(data, calculate(data), tmp_path / "defaults.docx")
    rows = [[cell.text for cell in row.cells] for row in Document(path).tables[0].rows]
    co2 = next(row for row in rows if row[0] == "室内二氧化碳浓度限值")
    assert co2[1] == "1000" and co2[-1] == "GB/T 18883-2022 第4.2条、表1"


def test_negative_zero_and_density_user_input(tmp_path):
    from openresivent.household_check import _one, save_report

    assert _one(-0.000001) == "0.0"
    assert _one(-0.1) == "-0.1"
    raw = yaml.safe_load((ROOT / "cases/workflows/household_example.yaml").read_text())
    raw["sources"]["dwelling_pressure.density_kg_m3"] = "用户输入"
    data = HouseholdCheck.model_validate(raw)
    path = save_report(data, calculate(data), tmp_path / "user.docx")
    rows = [[cell.text for cell in row.cells] for row in Document(path).tables[0].rows]
    assert next(row for row in rows if row[0] == "空气密度")[-1] == "用户输入"


def test_workflow_mismatch_rejected():
    raw = yaml.safe_load((ROOT / "cases/workflows/household_example.yaml").read_text())
    raw["dwelling"]["input"]["bedrooms"] = 2
    with pytest.raises(ValueError, match="卧室数量不一致"):
        calculate(HouseholdCheck.model_validate(raw))
    assert TestClient(app).post("/household-check", json=raw).status_code == 422
