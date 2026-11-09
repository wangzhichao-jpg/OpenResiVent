import json
from pathlib import Path

import pytest

from openresivent.core.case import Case, load_case
from openresivent.core.provenance import provenance
from openresivent.core.psychrometrics import (
    density,
    dew_point,
    enthalpy,
    humidity_ratio,
    mg_m3_to_ppm,
    ppm_to_mg_m3,
    pressure_at_altitude,
    relative_humidity,
    saturation_pressure,
)


def test_case_and_provenance(tmp_path: Path):
    case = tmp_path / "case.yaml"
    case.write_text("meta: {id: x, title: 示例}\nmodule: test\ninput: {}\n", encoding="utf8")
    assert load_case(case).meta.id == "x"
    assert len(provenance(case, {"test": "1"})["input_sha256"]) == 64
    assert json.loads(json.dumps(Case.model_json_schema()))["title"] == "Case"
    with pytest.raises(ValueError):
        Case.model_validate({"meta": {"id": "../x", "title": "x"}, "module": "x", "input": {}})


def test_psychrometrics():
    # Hyland & Wexler (1983), ASHRAE 2017 ch.1 equation 5/6, 0 ℃ triple-point vicinity.
    assert saturation_pressure(273.15) == pytest.approx(611.1536, rel=1e-4)
    assert pressure_at_altitude(0) == 101325
    assert pressure_at_altitude(1000) < 101325
    p, t = 101325, 293.15
    w = humidity_ratio(t, 0.5, p)
    assert relative_humidity(t, w, p) == pytest.approx(0.5)
    assert saturation_pressure(dew_point(t, 0.5)) == pytest.approx(0.5 * saturation_pressure(t))
    assert density(t, p) == pytest.approx(1.2041, rel=1e-3)
    assert density(t, p, w) < density(t, p)
    assert enthalpy(273.15, 0) == 0
    co2 = ppm_to_mg_m3(1000, 0.04401, t, p)
    assert mg_m3_to_ppm(co2, 0.04401, t, p) == pytest.approx(1000)
    for function, args in [
        (pressure_at_altitude, (12000,)),
        (saturation_pressure, (100,)),
        (humidity_ratio, (t, 1.1, p)),
        (humidity_ratio, (373.15, 1, 100)),
        (relative_humidity, (t, -1, p)),
        (relative_humidity, (t, 1, p)),
        (dew_point, (t, 0)),
        (enthalpy, (t, -1)),
        (density, (0, p)),
        (ppm_to_mg_m3, (-1, 0.044, t, p)),
        (mg_m3_to_ppm, (1, 0, t, p)),
    ]:
        with pytest.raises(ValueError):
            function(*args)
