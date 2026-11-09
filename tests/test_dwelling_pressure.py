"""单区补风和开门力基准。"""

import pytest

from openresivent.dwelling.pressure import door_opening_force, single_zone


def test_makeup_and_exhaust():
    x = single_zone(250, 1 / 3600, exhaust=300 / 3600, opening_area=0.02)
    assert x["pressure_pa"] == pytest.approx(-12.598015, rel=1e-6)
    assert x["opening_m3_s"] * 3600 == pytest.approx(197.951675, rel=1e-6)
    assert x["leakage_m3_s"] * 3600 == pytest.approx(102.048325, rel=1e-6)
    assert not x["negative_pressure_warning"]
    x = single_zone(250, 1 / 3600, exhaust=127.5 / 3600, supply=150 / 3600)
    assert x["pressure_pa"] == pytest.approx(1.230587, rel=1e-6)
    x = single_zone(250, 1 / 3600, exhaust=300 / 3600, supply=150 / 3600)
    assert x["pressure_pa"] == pytest.approx(-22.785798, rel=1e-6)
    assert x["negative_pressure_warning"]


def test_door_force():
    assert door_opening_force(0.9, 2.1, 0.06, 66.1892265) == pytest.approx(67.016592, rel=1e-6)
    with pytest.raises(ValueError):
        door_opening_force(0.9, 2.1, 0.9, 0)
