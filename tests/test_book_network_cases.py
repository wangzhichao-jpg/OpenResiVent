"""CLI 非稳态及 PAH 风险输入输出和单位转换。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("name", "key"), [("ex2-04", "target_time_s"), ("ex2-06", "teq_kg_m3")])
def test_new_case(name, key, tmp_path):
    result = CliRunner().invoke(
        app, ["run", str(ROOT / "cases/book/ch02" / f"{name}.yaml"), "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.exception
    payload = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf8"))
    if name == "ex2-04":
        assert payload[key] / 3600 == pytest.approx(2.8802193864)
    else:
        assert payload[key] == pytest.approx(1.25e-12)
        assert "pah_tef.yaml" in payload["provenance"]["data_sha256"]
        assert payload["icr"] == pytest.approx(1.25e-12 * 0.087e9 * 2 / 24 * 350 / 365 * 52 / 70)
        assert len(payload["sensitivity"]) == 3


@pytest.mark.parametrize(
    ("name", "chapter"),
    [
        ("ex2-02", "ch02"),
        ("ex6-02", "ch06"),
        ("ex6-03", "ch06"),
        ("ex6-04", "ch06"),
        ("ex6-05", "ch06"),
    ],
)
def test_other_case(name, chapter, tmp_path):
    result = CliRunner().invoke(
        app, ["run", str(ROOT / "cases/book" / chapter / f"{name}.yaml"), "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.exception
    payload = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf8"))
    assert (tmp_path / f"{name}.md").exists()
    if name == "ex2-02":
        assert payload["bedrooms"][0]["D"] * 3600 == pytest.approx(1.2 / 0.07)
    elif name == "ex6-02":
        assert payload["efficiency"] == pytest.approx(0.5, abs=0.005)
        assert len(payload["local_ages_s"]) == 2
        assert "ex6-02.csv" in payload["provenance"]["data_sha256"]
    elif name == "ex6-03":
        assert payload["injection_flow_m3_s"] * 3600 == pytest.approx(100)
    elif name == "ex6-04":
        assert payload["duct_m3_s"] * 3600 == pytest.approx(360)
    else:
        assert payload["total_flow"]["deviation"] == pytest.approx(-0.075)
        assert not payload["terminal_flow"]["passed"]
        assert payload["continuous"]["selected_days"] == [f"2026-01-{d:02}" for d in range(26, 31)]
