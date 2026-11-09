"""扫描确定性、持久续算及独立算例对照。"""

import csv
import json
import sqlite3
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.sweep import run_sweep, samples, statistics

ROOT = Path(__file__).resolve().parents[1]


def example():
    base = yaml.safe_load((ROOT / "cases/book/ch02/ex2-01.yaml").read_text())
    spec = {
        "method": "factorial",
        "factors": {"occupants": {"values": [1, 2, 3]}, "co2_outdoor_ppm": {"values": [400, 420]}},
        "metrics": {"flow": "flow_m3_s"},
        "criteria": {"flow": {"op": "min", "limit": 0.01}},
    }
    return spec, base


def test_factorial_resume_and_cli(tmp_path):
    spec, base = example()
    out = tmp_path / "out"
    assert run_sweep(spec, base, out, 2)["completed"] == 6
    original = (out / "samples.csv").read_bytes()
    with sqlite3.connect(out / "samples.sqlite3") as db:
        before = db.execute("select payload from samples where id=0").fetchone()[0]
        db.execute("delete from samples where id>=3")
    run_sweep(spec, base, out, 2)
    assert (out / "samples.csv").read_bytes() == original
    with sqlite3.connect(out / "samples.sqlite3") as db:
        assert db.execute("select payload from samples where id=0").fetchone()[0] == before
    with (out / "samples.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for row in rows[:3]:
        c = json.loads(json.dumps(base))
        c["input"]["occupants"] = int(row["occupants"])
        c["input"]["co2_outdoor_ppm"] = int(row["co2_outdoor_ppm"])
        p = tmp_path / "case.yaml"
        p.write_text(yaml.safe_dump(c))
        run = CliRunner().invoke(app, ["run", str(p), "--out", str(tmp_path / "individual")])
        assert run.exit_code == 0, run.exception
        result = json.loads((tmp_path / "individual" / f"{c['meta']['id']}.json").read_text())
        assert float(row["flow"]) == result["flow_m3_s"]
    assert (out / "results.xlsx").exists() and (out / "summary.docx").exists()
    assert json.loads((out / "statistics.json").read_text())["metrics"]["flow"]["min"] == min(
        float(r["flow"]) for r in rows
    )
    modified = dict(spec, method="lhs")
    with pytest.raises(ValueError):
        run_sweep(modified, base, out)


def test_api_job(tmp_path, monkeypatch):
    import time

    from fastapi.testclient import TestClient

    from openresivent.api import app as api

    spec, base = example()
    client = TestClient(api)
    monkeypatch.setenv("ORV_SWEEP_DIR", str(tmp_path))
    r = client.post("/sweep", json={"spec": spec, "case": base, "out": "api", "workers": 1})
    assert r.status_code == 202, r.text
    job = r.json()["job_id"]
    for _ in range(200):
        state = client.get("/sweep/" + job).json()
        if state["status"] != "running":
            break
        time.sleep(0.05)
    assert state["status"] == "completed", state
    assert state["completed"] == 6
    assert client.get(f"/sweep/{job}/results").json()["metrics"]["flow"]["min"] > 0
    for filename in ("samples.csv", "results.xlsx", "summary.docx"):
        assert client.get(f"/sweep/{job}/files/{filename}").status_code == 200
    assert client.get(f"/sweep/{job}/files/samples.sqlite3").status_code == 404


def test_api_rejects_unsafe_sweep_directory(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from openresivent.api import app as api

    spec, base = example()
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("ORV_SWEEP_DIR", str(root))
    client = TestClient(api)
    for path in ("../escape", "/tmp/out", "..", "a/b", "a\\\\b"):
        assert (
            client.post("/sweep", json={"spec": spec, "case": base, "out": path}).status_code == 422
        )
    (root / "link").symlink_to(outside, target_is_directory=True)
    assert (
        client.post("/sweep", json={"spec": spec, "case": base, "out": "link"}).status_code == 422
    )
    (root / "inside").mkdir()
    (root / "inside" / "samples.csv").symlink_to(outside / "bad")
    assert (
        client.post("/sweep", json={"spec": spec, "case": base, "out": "inside"}).status_code == 422
    )


def test_lhs_result_repeatability(tmp_path):
    import numpy as np
    from scipy.stats import rankdata

    _, base = example()
    spec = {
        "method": "lhs",
        "seed": 827,
        "count": 12,
        "factors": {"occupants": {"range": [1, 4]}, "co2_outdoor_ppm": {"range": [350, 450]}},
        "metrics": {"flow": "flow_m3_s"},
    }
    run_sweep(spec, base, tmp_path / "first", 2)
    run_sweep(spec, base, tmp_path / "second", 2)
    a = (tmp_path / "first/samples.csv").read_bytes()
    b = (tmp_path / "second/samples.csv").read_bytes()
    assert a == b
    with (tmp_path / "first/samples.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    x = np.array([[float(r[k]) for k in spec["factors"]] for r in rows])
    y = rankdata([float(r["flow"]) for r in rows])
    x = np.column_stack([rankdata(x[:, i]) for i in range(x.shape[1])])
    x = (x - x.mean(axis=0)) / x.std(axis=0)
    y = (y - y.mean()) / y.std()
    independent = np.linalg.lstsq(x, y, rcond=None)[0]
    found = json.loads((tmp_path / "first/statistics.json").read_text())["sensitivity"]
    assert [s["value"] for s in found] == pytest.approx(independent, abs=1e-9)


def test_lhs_categorical_groups():
    spec = {
        "method": "lhs",
        "factors": {"fan": {"values": ["ordinary", "common"]}},
        "metrics": {"flow": "flow"},
    }
    rows = [
        {"factors": {"fan": "ordinary"}, "metrics": {"flow": 1.0}},
        {"factors": {"fan": "common"}, "metrics": {"flow": 2.0}},
        {"factors": {"fan": "ordinary"}, "metrics": {"flow": 1.1}},
        {"factors": {"fan": "common"}, "metrics": {"flow": 2.1}},
    ]
    out = statistics(rows, spec)
    assert len(out["groups"]) == 2 and out["sensitivity"][0]["value"] > 0


def test_public_rule_group_rates():
    rows = [
        {"factors": {"group": 1}, "metrics": {"noise": 30.0}},
        {"factors": {"group": 1}, "metrics": {"noise": 36.0}},
    ]
    spec = {
        "method": "factorial",
        "factors": {"group": {"values": [1]}},
        "metrics": {"noise": "noise"},
        "criteria": {"noise": {"pack": "GB55016-2021", "rule": "GB55016-2021:2.1.4:sleep"}},
    }
    result = statistics(rows, spec)
    assert result["groups"][0]["pass_rate"] == 0.5
    assert result["metrics"]["noise"]["p50"] == 33


def test_lhs_repeatability():
    spec = {
        "method": "lhs",
        "seed": 123,
        "count": 12,
        "factors": {"x": {"range": [0, 1]}, "y": {"range": [2, 4]}},
    }
    assert samples(spec) == samples(spec)
    rows = [{"factors": p, "metrics": {"v": 2 * p["x"] + p["y"]}} for p in samples(spec)]
    stat = statistics(rows, dict(spec, metrics={"v": "v"}))
    assert len(stat["sensitivity"]) == 2
