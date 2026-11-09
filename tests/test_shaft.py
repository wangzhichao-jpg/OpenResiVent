"""M3 高层竖井基准与扫描。"""

import math
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from scipy.optimize import brentq

from openresivent.shaft.model import (
    ShaftConfig,
    active_floors,
    build_network,
    calculate,
    fan_curve,
    scan_csv,
    valve_leakage,
)

TARGETS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "cases/benchmarks/targets.yaml").read_text(
        encoding="utf8"
    )
)


def test_fan_ratings_and_resistance():
    expected = dict(
        zip(("ordinary", "common", "high"), TARGETS["P202_A07_A08"]["values"], strict=True)
    )
    for name, value in expected.items():
        assert fan_curve(name).q_max * 3600 == pytest.approx(value, rel=1e-6)
    fan = fan_curve("ordinary")
    resistance = 0.0005 * 3600**2
    q = brentq(lambda x: fan.flow(-resistance * x * x)[0] - x, 0, fan.q_max)
    assert q * 3600 == pytest.approx(TARGETS["P202_A09"]["values"][0], rel=1e-6)
    assert resistance * q * q == pytest.approx(TARGETS["P202_A09"]["values"][1], rel=1e-6)
    with pytest.raises(ValueError):
        fan_curve("unknown")


def test_valve_and_distribution():
    assert valve_leakage(150 / 3600, 0.2, 250) * 3600 == pytest.approx(
        TARGETS["P202_A10"]["values"][0], rel=1e-6
    )
    assert valve_leakage(150 / 3600, 0.2, 100) * 3600 == pytest.approx(
        TARGETS["P202_A10"]["values"][1], rel=1e-6
    )
    for how in ("lower", "upper", "uniform", "random"):
        x = active_floors(6, 0.5, how, 42)
        assert len(x) == len(set(x)) == 3
        assert x == active_floors(6, 0.5, how, 42)
    with pytest.raises(ValueError):
        active_floors(0, 1, "uniform")
    with pytest.raises(ValueError):
        active_floors(6, 1, "bad")
    with pytest.raises(ValueError):
        valve_leakage(-1, 0.2, 100)


def test_qualitative_trends():
    base = ShaftConfig(floors=12, fraction=0.5)
    uniform = calculate(base)
    large = calculate(replace(base, width=0.75, depth=0.6))
    upper = calculate(replace(base, distribution="upper"))
    lower = calculate(replace(base, distribution="lower"))
    flows = [floor["exhaust_m3_s"] for floor in uniform["floors"] if floor["active"]]
    assert flows[0] == min(flows)
    assert large["std_m3_s"] < uniform["std_m3_s"]
    assert upper["total_exhaust_m3_s"] > uniform["total_exhaust_m3_s"] > lower["total_exhaust_m3_s"]


def test_pressure_reference_33_floors():
    from openresivent.core.psychrometrics import density
    from openresivent.network.solver import G

    c = ShaftConfig(floors=33, fraction=0.394)
    r = calculate(c)
    top = r["floors"][-1]
    z = (33 - 0.5) * c.floor_height
    assert 10 < top["shaft_to_outdoor_pa"] < 100
    assert top["shaft_to_outdoor_pa"] == pytest.approx(
        r["_zone_pressures_pa"]["shaft33"] + density(c.outside_temperature, 101325) * G * z
    )
    assert top["shaft_to_home_pa"] == pytest.approx(
        r["_zone_pressures_pa"]["shaft33"] - r["_zone_pressures_pa"]["home33"]
    )
    assert "shaft_pressure_pa" not in top


def test_model_and_scan(tmp_path):
    c = ShaftConfig(floors=6, fraction=0.5)
    zones, links, ids = build_network(c)
    assert len(ids["active"]) == 3 and len(ids["shaft"]) == 5
    assert len(zones) > 12 and len(links) > 15
    result = calculate(c)
    assert result["mass_residual_kg_s"] < 1e-9
    assert len(result["floors"]) == 6
    assert result["total_exhaust_m3_s"] > 0
    assert abs(result["thermal_additional_m3_s"]) < 1e-12
    cold = calculate(replace(c, outside_temperature=283.15))
    assert math.isfinite(cold["thermal_additional_m3_s"])
    dims = {
        "floors": [3],
        "sections": [(0.5, 0.4)],
        "fractions": [0.5, 1],
        "fan_kinds": ["ordinary"],
        "valve_classes": ["good", "medium"],
    }
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    assert scan_csv(c, dims, a) == 4
    assert scan_csv(c, dims, b) == 4
    assert a.read_bytes() == b.read_bytes()
    import csv

    with a.open(encoding="utf8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert "底层排风量（m³/h）" in rows[0]
    assert "非运行层最大倒灌风量（m³/h）" in rows[0]
    assert "最大倒灌楼层（层）" in rows[0]
    assert "顶层竖井相对同高度室外压差（Pa）" in rows[0]
    assert float(rows[0]["底层排风量（m³/h）"]) > 0
    assert rows[0]["最大倒灌楼层（层）"]
    assert {row["油烟机类型"] for row in rows} == {"普通型"}
    assert {row["止回阀等级"] for row in rows} == {"良好", "中等"}
    assert all("区压力" not in key for key in rows[0])
    with pytest.raises(ValueError):
        scan_csv(c, {}, a)
    with pytest.raises(ValueError):
        build_network(replace(c, valve_class="bad"))
