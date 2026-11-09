"""书稿算例和规则引擎的初步测试。"""

import math

import numpy as np
import pytest

from openresivent.measure.tracer import decay, read_csv, two_point
from openresivent.network.solver import (
    Link,
    Zone,
    flow_and_derivative,
    orifice_coefficient,
    solve,
    wind_pressure,
)
from openresivent.rules.engine import check_rule, load_pack
from openresivent.ventrate.calculation import (
    Room,
    air_changes_rate,
    ashrae_flow,
    calculate_dwelling,
    co2_flow,
    en_co2_flow,
)


def test_book_ventilation():
    assert co2_flow(3 * 18e-3 / 3600, 400e-6, 1000e-6) * 3600 == pytest.approx(90)
    assert ashrae_flow(90, 3) * 1000 == pytest.approx(27.5)
    assert en_co2_flow(1e-6, "II") == pytest.approx(1e-6 / 800e-6)
    assert [air_changes_rate(x) * 3600 for x in (10, 20, 50, 51)] == pytest.approx(
        [0.7, 0.6, 0.5, 0.45]
    )
    rooms = [Room(12, 2.8, 2), Room(10, 2.8, 1)]
    output = calculate_dwelling(90, 2.8, 3, rooms, Room(25, 2.8, 3))
    assert output["design"] >= output["only_440"]
    assert output["room_total"] == pytest.approx(
        sum(r["selected"] for r in output["bedrooms"])
        + max(output["living"]["A"], output["living"]["B"])
    )
    assert output["fan"] == pytest.approx(output["design"] * 1.05)
    assert calculate_dwelling(90, 2.8, 3, rooms, Room(25, 2.8, 3), include_people=False)[
        "design"
    ] == pytest.approx(output["only_440"])
    with pytest.raises(ValueError):
        co2_flow(1, 0.001, 0.0004)


def test_tracer(tmp_path):
    assert two_point(3000, 1500, 400, 1800) * 3600 == pytest.approx(1.72040253)
    rng = np.random.default_rng(7)
    times = np.linspace(0, 4 * 3600, 25)
    concentrations = 400 + 2000 * np.exp(-0.8 * times / 3600 + rng.normal(0, 0.01, len(times)))
    result = decay(times.tolist(), concentrations.tolist(), 400)
    assert result["ci95"][0] < 0.8 / 3600 < result["ci95"][1]
    assert result["local_age"] > 0
    path = tmp_path / "c.csv"
    path.write_text("time_s,p1,p2\n0,2,3\n1,1,2\n", encoding="utf8")
    assert read_csv(path)["p2"] == [3, 2]
    with pytest.raises(ValueError):
        decay([0, 1, 2], [400, 400, 400], 400)


def test_network():
    rho = 1.2
    temp = 101325 / (287.055 * rho)
    c = [orifice_coefficient(0.6, a, rho) for a in [1.5, 1.6, 1.2]]
    zones = {
        "south": Zone(temp, wind_pressure(0.6, rho, 3), fixed=True),
        "living": Zone(temp),
        "bed": Zone(temp),
        "north": Zone(temp, wind_pressure(-0.3, rho, 3), fixed=True),
    }
    links = [
        Link("south", "living", c[0], 0.5),
        Link("living", "bed", c[1], 0.5),
        Link("bed", "north", c[2], 0.5),
    ]
    result = solve(zones, links)
    expected = math.sqrt((3.24 + 1.62) / sum(1 / x**2 for x in c))
    assert result["flows"][0]["volume_flow"] == pytest.approx(expected, rel=1e-6)
    assert result["mass_residual"] < 1e-8
    assert flow_and_derivative(0, 1, 0.5)[0] == 0


def test_rule(tmp_path):
    path = tmp_path / "pack.yaml"
    path.write_text(
        'id: p\nversion: "1"\nrules:\n- id: x\n  title: test\n  strength: 应\n  params: {}\n  check: {op: min, limit: 2}\n  source: 转述\n',
        encoding="utf8",
    )
    rule = load_pack(path)["rules"][0]
    assert check_rule(rule, 2)["passed"]
    assert not check_rule(rule, 1)["passed"]
    rule["check"]["limit"] = None
    with pytest.raises(ValueError):
        check_rule(rule, 1)
    assert check_rule(rule, 3, calculated_limit=2)["passed"]
