"""M8、M9 热压、风帽及风口条件。"""

import pytest

from openresivent.ventrate.air_distribution import indoor_outlets, jet, outdoor_intake
from openresivent.ventrate.natural import (
    book_double_opening,
    book_opening_heights,
    book_single_opening,
    coupled,
    double_opening,
    metrics,
    paper11_pressure_flow,
    paper12_cd,
    paper13_performance,
    paper13_threshold,
    single_opening,
    suitability,
)


def test_stack():
    q = single_opening(0.6, 1, 1.5, 10, 288.15)
    assert q == pytest.approx(0.142923, rel=1e-5)
    x = double_opening(0.6, 0.5, 0.5, 3, 10, 288.15)
    assert x["equivalent_area_m2"] == pytest.approx(0.353553, abs=5e-7)
    assert x["flow_m3_s"] == pytest.approx(0.303185, rel=1e-5)
    net = coupled(0.5, 0.5, 0.6, 3, 293.15, 283.15)
    mean_flow = sum(f["volume_flow"] for f in net["flows"]) / 2
    assert mean_flow == pytest.approx(x["flow_m3_s"], rel=0.02)
    assert coupled(0.5, 0.5, 0.6, 3, 293.15, 283.15, 3, 0.6, -0.3)["mass_residual"] < 1e-8
    with pytest.raises(ValueError):
        single_opening(0.6, 1, 1, -1, 288)


def test_book_opening_comparisons():
    import math

    a = book_single_opening(1, 1.5, 10)
    b = book_double_opening(1, 1, 1.5, 10)
    assert a == pytest.approx(0.04 * math.sqrt(15))
    assert b == pytest.approx(0.15 / math.sqrt(2) * math.sqrt(15))
    assert (a / single_opening(0.62, 1, 1.5, 10, 293) - 1) * 100 == pytest.approx(5.7764197)
    assert (b / double_opening(0.62, 1, 1, 1.5, 10, 293)["flow_m3_s"] - 1) * 100 == pytest.approx(
        -6.5059704
    )
    assert book_opening_heights(100) == {"hc_m": 3, "hk_m": 10}
    assert book_double_opening(0.5, 1, 2, 0) == 0
    for call in (
        lambda: book_opening_heights(0),
        lambda: book_single_opening(1, 1, -1),
        lambda: book_double_opening(1, float("nan"), 1, 1),
    ):
        with pytest.raises(ValueError):
            call()


def test_turbine():
    v = metrics(0.12, 0.10, 0.11)
    assert v["gamma_natural"] == pytest.approx(1.2)
    assert v["phi_static"] == pytest.approx(0.090909, rel=1e-5)
    assert not suitability(10, 5)["turbine_better_than_static"]
    assert paper11_pressure_flow(-5) == pytest.approx(0.208)
    assert paper12_cd(40) == 0.55
    assert paper13_threshold(10) == 11.5
    assert paper13_performance(10, 5)["phi"] < 0
    with pytest.raises(ValueError):
        paper13_performance(1000, 1)
    with pytest.raises(ValueError):
        paper13_threshold(31)


def test_outlets():
    j = jet(3, 0.15, 0.07, 2, 5, 0.25)
    assert j["velocity_m_s"] > 0 and j["throw_m"] > 0
    assert not indoor_outlets(3.2, "horizontal", 0.9)["speed_recommended"]
    assert not indoor_outlets(3.2, "horizontal", 0.9)["spacing_passed"]

    def f(h, v, below, layout="horizontal", ground=1.8, green=False):
        return outdoor_intake(
            "water_heater",
            h,
            v,
            intake_below=below,
            layout=layout,
            same_direction=True,
            ground_clearance=ground,
            green=green,
        )

    assert not f(1.2, 0, False)["pollution_passed"]
    assert f(0, 1.6, True, "vertical")["pollution_passed"]
    assert not f(0, 2, False, "vertical")["pollution_passed"]
    assert not f(0.8, 0, True)["decentral_passed"]
    assert not f(2, 0, True)["ground_recommended"]
    assert f(2, 0, True, ground=1.2, green=True)["ground_recommended"]
    with pytest.raises(ValueError):
        outdoor_intake(
            "bad",
            0,
            0,
            intake_below=True,
            layout="horizontal",
            same_direction=True,
            ground_clearance=2,
        )
