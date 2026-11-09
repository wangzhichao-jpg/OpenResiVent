"""\u5de5\u4f5c\u6307\u4ee4 A4–A10，均使用未四舍五入解析值比较。"""

import math
from pathlib import Path

import pytest

from openresivent.core.case import load_case
from openresivent.core.runner import execute
from openresivent.measure.tracer import two_point
from openresivent.network.fan import quadratic_fan_flow
from openresivent.network.solver import Link, Zone, orifice_coefficient, solve, wind_pressure
from openresivent.ventrate.calculation import ashrae_flow, co2_flow

ROOT = Path(__file__).resolve().parents[2]


def test_b01():
    assert co2_flow(3 * 0.018 / 3600, 400e-6, 1000e-6) * 3600 == pytest.approx(90, rel=1e-9)


def test_b02():
    assert ashrae_flow(90, 3) * 3600 == pytest.approx(99, rel=1e-9)


def test_b03():
    assert two_point(2600, 1100, 0, 1800) * 3600 == pytest.approx(1.7204, abs=0.0001)


def test_b05():
    q = quadratic_fan_flow(400 / 3600, 280, 200)
    assert q / (400 / 3600) == pytest.approx((1 - 200 / 280) ** 0.5, rel=1e-12)
    with pytest.raises(ValueError):
        quadratic_fan_flow(1, 280, 281)


@pytest.mark.parametrize("speed", [3, 1.5])
def test_b06(speed):
    rho = 1.2
    temp = 101325 / (287.055 * rho)
    c = [orifice_coefficient(0.6, a, rho) for a in (1.5, 1.6, 1.2)]
    z = {
        "south": Zone(temp, wind_pressure(0.6, rho, speed), fixed=True),
        "a": Zone(temp),
        "b": Zone(temp),
        "north": Zone(temp, wind_pressure(-0.3, rho, speed), fixed=True),
    }
    r = solve(
        z, [Link("south", "a", c[0], 0.5), Link("a", "b", c[1], 0.5), Link("b", "north", c[2], 0.5)]
    )
    expected = math.sqrt((0.5 * 0.9 * rho * speed**2) / sum(1 / ci**2 for ci in c))
    assert r["flows"][0]["volume_flow"] == pytest.approx(expected, rel=1e-6)
    assert r["mass_residual"] < 1e-8


def test_b04():
    p = ROOT / "cases/book/ch05/ex5-01.yaml"
    result, _ = execute(load_case(p), p)
    expected = 9.81 * 100 * 101325 / 287.055 * (1 / 263.15 - 1 / 293.15)
    assert result["stack"]["total_pressure_pa"] == pytest.approx(expected, abs=0.05)
    assert 0 < result["stack"]["neutral_height_m"] < 100
    assert sum(abs(f["delta_p"]) for f in result["flows"]) == pytest.approx(expected, abs=0.001)
    assert result["mass_residual"] < 1e-8
