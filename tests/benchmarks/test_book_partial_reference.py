"""\u0057\u004f\u002d\u00501-01 解析基准初步测试。"""

import pytest

from openresivent.health.risk import exposure_factor, hazard_quotient, icr, risk_category, teq
from openresivent.health.units import iur_per_ug_m3_to_per_kg_m3
from openresivent.measure.tracer import local_mean_air_age
from openresivent.measure.ventilation import (
    air_change_efficiency,
    measured_flow,
    tracer_flow,
    ventilation_effectiveness,
)
from openresivent.ventrate.pollutant import (
    concentration,
    steady_flow,
    time_to_95_percent,
    time_to_target,
)


def test_a7():
    assert steady_flow(1.2e-6 / 3600, 0.01e-6, 0.08e-6) * 3600 == pytest.approx(
        17.142857142857, rel=1e-9
    )


def test_a8_a9():
    assert time_to_target(1000e-9, 20e-9, 75e-9, 1 / 3600) / 3600 == pytest.approx(2.8802193864)
    assert concentration(20e-9, 20e-9, 5000e-9 / 3600, 50 / 3600, 50, 3600) / 1e-9 == pytest.approx(
        83.2120558829
    )
    assert time_to_95_percent(1 / 3600) / 3600 == pytest.approx(2.99573227355)


def test_a10_a11_a12():
    assert teq(
        {"BaP": 1, "BaA": 2, "Chr": 5}, {"BaP": 1, "BaA": 0.1, "Chr": 0.01}
    ) == pytest.approx(1.25)
    iur = iur_per_ug_m3_to_per_kg_m3(0.087)
    continuous = icr(1.25e-12, iur, 1)
    assert continuous == pytest.approx(1.0875e-4)
    assert icr(1.25e-12, iur, exposure_factor(2, 365, 30, 70)) == pytest.approx(3.8839285714e-6)
    assert hazard_quotient(0.02, 0.01) == 2
    assert risk_category(1e-5) == "潜在风险"


def test_a13_a14():
    assert tracer_flow(0.5e-3 / 60, 300e-6, 0) * 3600 == pytest.approx(100)
    import math

    times = [36 * i for i in range(601)]
    mixed = local_mean_air_age(times, [math.exp(-t / 3600) for t in times], tail_rate=1 / 3600)
    plug = local_mean_air_age([0, 3600], [1, 0])
    assert air_change_efficiency(3600, mixed) == pytest.approx(0.5, abs=0.005)
    assert air_change_efficiency(3600, plug) == pytest.approx(1, abs=0.005)
    assert measured_flow(2, 0.5, 0.8) == 0.8
    assert ventilation_effectiveness(10, 2, 6) == 2
