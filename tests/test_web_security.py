"""离线资源扫描、CSP、同源静态资源与嵌套字段。"""

import json
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from openresivent.api import app
from openresivent.web_security import AssetParser, scan

ROOT = Path(__file__).resolve().parents[1]


def test_scanner_detects_loading_not_plain_links(tmp_path):
    (tmp_path / "index.html").write_text('<script src="https://remote.test/x.js"></script>')
    assert scan(tmp_path)
    (tmp_path / "index.html").write_text('<script src="/assets/app.js"></script>')
    (tmp_path / "app.js").write_text('const doc="https://doc.test/"; fetch("/run");')
    assert not scan(tmp_path)
    (tmp_path / "app.js").write_text('fetch("https://remote.test/x")')
    assert scan(tmp_path)
    (tmp_path / "app.js").write_text('const x="https://doc.test/"')
    (tmp_path / "style.css").write_text('@import "https://remote.test/a.css";')
    assert scan(tmp_path)
    (tmp_path / "style.css").write_text("a{background:url(//remote.test/x)}")
    assert scan(tmp_path)
    (tmp_path / "style.css").write_text("a{background:url(data:image/png;base64,abc)}")
    (tmp_path / "app.js").write_text('const x=import("https://remote.test/x.js")')
    assert scan(tmp_path)
    (tmp_path / "app.js").write_text(
        'const x=new XMLHttpRequest();x.open("GET","https://remote.test/x")'
    )
    assert scan(tmp_path)
    (tmp_path / "app.js").write_text('fetch("http://127.0.0.1:8765/run")')
    assert not scan(tmp_path)


def test_built_assets_and_csp():
    root = ROOT / "build/web"
    if not (root / "index.html").is_file():
        pytest.skip("尚未构建前端资源")
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200 and "default-src 'self'" in r.headers["content-security-policy"]
    assert "connect-src 'self'" in r.headers["content-security-policy"]
    parser = AssetParser()
    parser.feed(r.text)
    assert parser.references
    for url in parser.references:
        if url.startswith("/"):
            assert client.get(url).status_code == 200, url
    assert not scan(root)
    text = "\n".join(p.read_text(errors="ignore") for p in root.rglob("*") if p.is_file())
    assert not re.search(r"\u5de5\u4f5c\u6307\u4ee4|\u0057\u004f\u002d\u0050\d|\u7ba1\u7406\u7aef|JGJT\d{3,}-\d{4}|GBT\d{3,}-\d{4}", text)


def test_nested_fields():
    client = TestClient(app)
    d = yaml.safe_load((ROOT / "cases/book/ch02/ex2-03.yaml").read_text())
    d["input"]["bedrooms"][0]["area_m2"] = "错误"
    r = client.post("/run", json=d)
    assert r.status_code == 422 and "input.bedrooms.0.area_m2" in r.text and "应为数字" in r.text
    d = yaml.safe_load((ROOT / "cases/book/ch02/ex2-03.yaml").read_text())
    d["input"]["living"]["hcho_materials"] = [{"area_m2": 1}]
    r = client.post("/run", json=d)
    assert r.status_code == 422 and "input.living.hcho_materials.0.ef_mg_m2_h" in r.text
    d = yaml.safe_load((ROOT / "cases/reports/shaft_example.yaml").read_text())
    del d["input"]["dwelling"]["hood_m3_h"]
    r = client.post("/report?type=shaft", json=d)
    assert r.status_code == 422 and "input.dwelling.hood_m3_h" in r.text
    d = json.loads(json.dumps(d))
    d["input"]["dwelling"]["hood_m3_h"] = 300
    d["input"]["shaft"]["floors"] = "十"
    r = client.post("/report?type=shaft", json=d)
    assert r.status_code == 422 and "input.shaft.floors" in r.text
    d = yaml.safe_load((ROOT / "cases/book/ch04/ex4-11.yaml").read_text())
    d["input"]["effectiveness"][0] = "错误"
    r = client.post("/run", json=d)
    assert r.status_code == 422 and "input.effectiveness.0" in r.text
    d = yaml.safe_load((ROOT / "cases/book/ch06/ex6-06.yaml").read_text())
    d["input"]["fan_power_w"] = "错误"
    r = client.post("/run", json=d)
    assert r.status_code == 422 and "input.fan_power_w" in r.text
    d = yaml.safe_load((ROOT / "cases/reports/commissioning_example.yaml").read_text())
    del d["input"]["acceptance"]["seed"]
    r = client.post("/report?type=commissioning", json=d)
    assert r.status_code == 422 and "input.acceptance.seed" in r.text
