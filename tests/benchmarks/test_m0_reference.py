"""文献参考点与焓湿自洽验证。"""

from pathlib import Path

import pytest
import yaml

from openresivent.core.psychrometrics import (
    dew_point,
    enthalpy,
    humidity_ratio,
    relative_humidity,
    saturation_pressure,
)

TARGETS = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "cases/benchmarks/targets.yaml").read_text()
)


@pytest.mark.parametrize("point", TARGETS["M0_saturation"]["points"])
def test_m0_saturation(point):
    assert saturation_pressure(point["temperature_c"] + 273.15) == pytest.approx(
        point["pressure_pa"], rel=0.001
    )


@pytest.mark.parametrize(
    ("temperature", "rh", "pressure"),
    [(293.15, 0.5, 101325), (298.15, 0.8, 101325), (263.15, 0.6, 90000)],
)
def test_m0_inverse(temperature, rh, pressure):
    w = humidity_ratio(temperature, rh, pressure)
    assert relative_humidity(temperature, w, pressure) == pytest.approx(rh, rel=1e-9)
    assert saturation_pressure(dew_point(temperature, rh)) == pytest.approx(
        rh * saturation_pressure(temperature), rel=1e-9
    )
    t = temperature - 273.15
    h = enthalpy(temperature, w)
    assert (h / 1000 - 1.006 * t) / (2501 + 1.86 * t) == pytest.approx(w, rel=1e-9)
