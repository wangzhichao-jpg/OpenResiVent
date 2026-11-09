"""论文图风机读数及 CAV / PID 工作点。"""

import pytest

from openresivent.energy.fan_figures import (
    CAV_P,
    PID_P,
    Q_H,
    electrical_power,
    interpolate,
    pressure,
)
from openresivent.energy.model import ControlConfig, control_step


def test_digitized_curves():
    assert pressure(210 / 3600, "cav") == pytest.approx(CAV_P[2])
    assert pressure(210 / 3600, "pid") == pytest.approx(PID_P[2])
    assert pressure(227.5 / 3600, "cav") == pytest.approx((CAV_P[2] + CAV_P[3]) / 2)
    assert electrical_power(180 / 3600, "pid", on_design=True) == 96
    assert electrical_power(280 / 3600, "cav") == pytest.approx(0.2316 * 280 + 20.679)
    assert len(Q_H) == 7
    with pytest.raises(ValueError):
        pressure(1, "other")
    with pytest.raises(ValueError):
        interpolate(-1, CAV_P)


def test_initial_and_out_of_chart():
    c = ControlConfig(fan_model="paper_digitized")
    clean = control_step("cav", 0, c)
    assert 140 < clean["flow_m3_s"] * 3600 < 350
    assert clean["fan_power_w"] > 0
    assert not clean["curve_extrapolated"]
    assert control_step("pid", 0, c)["fan_power_w"] == 96
    assert control_step("cav", 0.1, c)["curve_extrapolated"]
