"""产品检测公开函数和端到端算例。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.measure.product import (
    exchange_efficiency,
    fan_law,
    purification_efficiency,
    specific_power,
)


def test_exchange():
    def f(m):
        return exchange_efficiency(m, 0.04, 273.15, 293.15, 288.15, 0.002, 0.008, 0.005)

    assert f(0.04)["sensible"] == pytest.approx(0.75)
    assert f(0.05)["sensible"] == pytest.approx(0.9375)
    assert f(0.05)["latent"] == pytest.approx(0.625)
    with pytest.raises(ValueError):
        f(0)
    with pytest.raises(ValueError):
        exchange_efficiency(0.05, 0.04, 273, 273, 273, 0.002, 0.008, 0.005)


def test_fan_and_power():
    f = fan_law(180 / 3600, 80, 45, 1.1)
    assert f["flow_m3_s"] * 3600 == pytest.approx(198)
    assert f["pressure_pa"] == pytest.approx(96.8)
    assert f["power_w"] == pytest.approx(59.895)
    s = specific_power(150 / 3600, 45)
    assert s["w_per_m3_h"] == pytest.approx(0.3) and s["sfp_w_per_m3_s"] == pytest.approx(1080)
    with pytest.raises(ValueError):
        specific_power(0, 45)
    with pytest.raises(ValueError):
        fan_law(0, 80, 45, 1)


def test_purification():
    assert purification_efficiency(150 / 3600, 0.9, 45, "dual")["grade"] == "节能级"
    assert purification_efficiency(150 / 3600, 0.87, 45, "dual")["grade"] == "合格级"
    assert purification_efficiency(150 / 3600, 0.01, 45, "single")["grade"] == "未达到合格级"
    with pytest.raises(ValueError):
        purification_efficiency(1, 2, 45, "dual")


def test_example(tmp_path):
    p = Path(__file__).resolve().parents[1] / "cases/book/ch06/ex6-06.yaml"
    r = CliRunner().invoke(app, ["run", str(p), "--out", str(tmp_path)])
    assert r.exit_code == 0, r.exception
    data = json.loads((tmp_path / "ex6-06.json").read_text())
    text = (tmp_path / "ex6-06.md").read_text()
    assert data["exchange"]["sensible"] == pytest.approx(0.9375)
    assert "93.75%" in text and "节能级" in text and len(data["provenance"]["input_sha256"]) == 64
