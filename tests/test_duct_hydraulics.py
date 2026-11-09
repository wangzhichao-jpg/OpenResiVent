"""风管水力解析值和工程边界测试。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.duct.hydraulics import (
    DuctSegment,
    airflow_properties,
    balance,
    balance_parallel_flows,
    fan_allowance,
    fan_operating_point,
    friction_factor,
    network,
)
from openresivent.network.elements import PolynomialFan


def test_wop103_a6_a8():
    a = DuctSegment("a", 10, 200 / 3600, 0.00015, diameter=0.16, local_zeta=0.3)
    x = a.calculate(1.2, 1.5e-5)
    for key, expected in [
        ("velocity_m_s", 2.763107),
        ("reynolds", 29473.1),
        ("friction_factor", 0.025906),
        ("friction_pa", 7.416836),
        ("dynamic_pressure_pa", 4.580855),
        ("local_pa", 1.374257),
    ]:
        assert x[key] == pytest.approx(expected, rel=1e-4)
    b = DuctSegment("b", 5, 60 / 3600, 0.00015, diameter=0.1).calculate(1.2, 1.5e-5)
    assert b["friction_factor"] == pytest.approx(0.030804, rel=1e-4)
    assert b["friction_pa"] == pytest.approx(4.161417, rel=1e-4)
    assert x["recommended_speed_passed"] and x["maximum_speed_passed"]
    main = DuctSegment("a", 10, 200 / 3600, 0.00015, diameter=0.16, role="main").calculate(
        1.2, 1.5e-5
    )
    assert not main["recommended_speed_passed"] and main["maximum_speed_passed"]


def test_balance_and_fan():
    assert balance(60, 48) == {"fraction": 0.2, "recommended_passed": False}
    r = fan_allowance(200 / 3600, 150, flow_unit="m3/s")
    with pytest.raises(ValueError, match="m3/s"):
        fan_allowance(200, 150, flow_unit="m3/h")
    with pytest.raises(TypeError):
        fan_allowance(200, 150)
    assert [x * 3600 for x in r["flow_m3_s"]] == pytest.approx([210, 220])
    assert r["pressure_pa"] == pytest.approx((165, 172.5))


def test_geometry_and_edges():
    rho, nu = airflow_properties(293.15, 101325)
    s = DuctSegment("x", 10, 0.03, 0.00015, width=0.2, height=0.1)
    assert s.calculate(rho, nu)["hydraulic_diameter_m"] == pytest.approx(2 * 0.2 * 0.1 / 0.3)
    assert friction_factor(1000, 0.001) == pytest.approx(0.064)
    assert friction_factor(20000, 0.001, "altshul") > 0
    assert friction_factor(3000, 0.001) > 0
    with pytest.raises(ValueError):
        airflow_properties(0, 101325)
    with pytest.raises(ValueError):
        balance(0, 0)
    x = network({"x": s}, {"room": ["x"]}, rho, nu)
    assert x["critical_route"] == "room" and x["pressure_pa"] > 0
    fan = PolynomialFan((280, 0, -280 / (400 / 3600) ** 2), 400 / 3600)
    point = fan_operating_point(fan, {"x": s}, ["x"], rho, nu, (0.72, 0.8))
    assert point["flow_m3_s"] > 0 and point["efficiency_passed"]
    with pytest.raises(ValueError):
        fan_operating_point(fan, {"x": s}, ["wrong"], rho, nu)
    with pytest.raises(ValueError):
        fan_operating_point(fan, {"x": s}, ["x"], rho, nu, (0.9, 0.8))
    with pytest.raises(ValueError):
        DuctSegment("x", 1, 1, 0).calculate(rho, nu)
    with pytest.raises(ValueError):
        DuctSegment("x", 1, 1, 0, diameter=0.1, role="invalid").calculate(rho, nu)
    with pytest.raises(ValueError):
        friction_factor(1000, 0, "invalid")
    with pytest.raises(ValueError):
        fan_allowance(0, 1, flow_unit="m3/s")
    with pytest.raises(ValueError):
        network({"x": s}, {"broken": ["missing"]}, rho, nu)


def test_parallel_balance():
    segments = {
        "main": DuctSegment("main", 5, 0.05, 0.00015, diameter=0.2, role="main"),
        "left": DuctSegment("left", 4, 0.025, 0.00015, diameter=0.12),
        "right": DuctSegment("right", 8, 0.025, 0.00015, diameter=0.12),
    }
    result = balance_parallel_flows(
        segments, {"L": ["main", "left"], "R": ["main", "right"]}, 0.05, 1.2, 1.5e-5
    )
    assert sum(result["terminal_flows_m3_s"].values()) == pytest.approx(0.05, rel=1e-9)
    assert result["terminal_flows_m3_s"]["L"] > result["terminal_flows_m3_s"]["R"]
    assert result["route_losses_pa"]["L"] == pytest.approx(result["route_losses_pa"]["R"], rel=1e-8)
    assert result["segment_flows_m3_s"]["main"] == pytest.approx(0.05)
    with pytest.raises(ValueError):
        balance_parallel_flows(
            segments, {"a": ["main", "left"], "b": ["main", "left"]}, 0.05, 1.2, 1.5e-5
        )


@pytest.mark.parametrize("case", ["ch02/ex2-09", "ch04/ex4-08"])
def test_duct_case(case, tmp_path):
    root = Path(__file__).resolve().parents[1]
    path = root / "cases/book" / f"{case}.yaml"
    r = CliRunner().invoke(app, ["run", str(path), "--out", str(tmp_path)])
    assert r.exit_code == 0, r.exception
    data = json.loads((tmp_path / f"{path.stem}.json").read_text())
    assert data["pressure_pa"] > 0 and data["fan_allowance"]
    if path.stem == "ex4-08":
        assert data["fan_operating_point"]["flow_m3_s"] > 0
