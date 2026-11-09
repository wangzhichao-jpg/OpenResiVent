"""API 示例、输入校验及临时文件清理。"""

import io
import json
from pathlib import Path

import pytest
import yaml
from docx import Document
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from openresivent.api import app
from openresivent.cli import app as cli

ROOT = Path(__file__).resolve().parents[1]


def case(chapter, name):
    return yaml.safe_load((ROOT / "cases/book" / chapter / f"{name}.yaml").read_text())


def test_run(tmp_path):
    client = TestClient(app)
    r = client.post("/run", json=case("ch02", "ex2-01"))
    assert r.status_code == 200, r.text
    assert r.json()["flow_m3_s"] * 3600 == pytest.approx(90)
    payload = case("ch05", "ex5-07")
    r = client.post("/run", json=payload)
    assert r.status_code == 200, r.text
    source = ROOT / "cases/book/ch05/ex5-07.yaml"
    run = CliRunner().invoke(cli, ["run", str(source), "--out", str(tmp_path)])
    assert run.exit_code == 0
    expected = json.loads((tmp_path / "ex5-07.json").read_text())
    assert r.json()["scenarios"] == expected["scenarios"]
    assert client.post("/run", json={"module": "co2", "input": {}}).status_code == 422
    assert "请求字段" in client.post("/run", json={}).text
    bad = case("ch02", "ex2-01")
    del bad["input"]["occupants"]
    assert client.post("/run", json=bad).status_code == 422
    assert client.get("modules").status_code == 200
    rows = client.get("/rules").json()["rules"]
    assert rows and all(r["standard"] and r["clause"] and r["requirement"] for r in rows)


def test_public_names_and_fields():
    client = TestClient(app)
    modules = client.get("/modules").json()["modules"]
    assert "dwelling_pressure" in modules and "ductless" in modules and "shaft" in modules
    assert not any(x.startswith(("p2_", "p3_", "p" + "303_", "m4_")) for x in modules)
    payload = case("ch05", "ex5-07")
    payload["module"] = "p2_dwelling"
    with pytest.warns(FutureWarning):
        r = client.post("/run", json=payload)
    assert r.status_code == 200 and r.headers["Deprecation"] == "true"
    p = case("ch02", "ex2-01")
    p["input"]["occupants"] = "三"
    r = client.post("/run", json=p)
    assert r.status_code == 422 and "input.occupants" in r.text and "应为数字" in r.text
    del p["input"]["occupants"]
    r = client.post("/run", json=p)
    assert r.status_code == 422 and "input.occupants" in r.text and "必填" in r.text
    invalid = case("ch02", "ex2-01")
    invalid["module"] = "invalid"
    assert client.post("/run", json=invalid).status_code == 422
    from openresivent.core.module_names import ALIASES

    for p in (ROOT / "cases").rglob("*.yaml"):
        data = yaml.safe_load(p.read_text())
        if isinstance(data, dict) and "module" in data:
            assert data["module"] not in ALIASES


def test_inverse_makeup_api():
    client = TestClient(app)
    payload = yaml.safe_load((ROOT / "cases/studies/makeup_base.yaml").read_text())
    response = client.post("/run", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mechanical"]["value"] > 0
    assert result["opening"]["value"] > 0
    del payload["input"]["n50_per_h"]
    assert client.post("/run", json=payload).status_code == 422


def test_serve_defaults(monkeypatch):
    import uvicorn

    called = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: called.update(kw))
    result = CliRunner().invoke(cli, ["serve"])
    assert result.exit_code == 0 and called["host"] == "127.0.0.1" and called["port"] == 8765


def test_reports(tmp_path):
    client = TestClient(app)
    for p, t in [(case("ch02", "ex2-03"), "design"), (case("ch05", "ex5-07"), "design")]:
        r = client.post("/report?type=" + t, json=p)
        assert r.status_code == 200, r.text
        api_doc = Document(io.BytesIO(r.content))
        assert "设计计算" in api_doc.paragraphs[0].text
        from openresivent.core.case import Case
        from openresivent.report.docx_report import document_text

        path = tmp_path / "case.yaml"
        path.write_text(yaml.safe_dump(Case.model_validate(p).model_dump(), allow_unicode=True))
        command = CliRunner().invoke(
            cli, ["report", str(path), "--format", "docx", "--out", str(tmp_path)]
        )
        assert command.exit_code == 0, command.exception
        cli_doc = Document(tmp_path / f"{p['meta']['id']}.docx")
        assert document_text(api_doc) == document_text(cli_doc)
    assert client.post("/report?type=bad", json=case("ch02", "ex2-03")).status_code == 422
    for name, kind in [("shaft_example", "shaft"), ("commissioning_example", "commissioning")]:
        payload = yaml.safe_load((ROOT / "cases/reports" / f"{name}.yaml").read_text())
        r = client.post("/report?type=" + kind, json=payload)
        assert r.status_code == 200, r.text
        assert Document(io.BytesIO(r.content)).paragraphs[0].text
