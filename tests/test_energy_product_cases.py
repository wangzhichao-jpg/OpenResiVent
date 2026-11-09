"""三个新增算例及风机调速边界。"""

import json
import os
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.energy.model import ControlConfig, control_step
from openresivent.energy.operation_comparison import ductless

ROOT = Path(__file__).resolve().parents[1]


def test_free_cooling():
    from openresivent.energy.operation_comparison import guangzhou
    from openresivent.energy.weather import WeatherHour

    d = {
        "volume_m3": 100,
        "mechanical_ach": 0.8,
        "indoor_t_k": 299.15,
        "indoor_humidity_ratio": 0.01,
        "dry_density": 1.2,
        "enthalpy_efficiency": 0.6,
    }
    rows = [WeatherHour(7, 1, 1, 290.15, 0.005), WeatherHour(7, 1, 2, 305.15, 0.02)]
    result = guangzhou(d, rows)
    assert result["free_cooling_hours"] == 1
    assert result["free_cooling_with_bypass_j"] > result["free_cooling_without_bypass_j"] > 0
    assert result["cooling_with_bypass_j"] == pytest.approx(result["cooling_without_bypass_j"])


def test_vav():
    c = ControlConfig(fan_model="paper_digitized")
    for g in range(0, 41, 5):
        p = control_step("pid", g / 1000, c)
        v = control_step("vav", g / 1000, c)
        assert p["target_met"] and v["target_met"]
        assert v["flow_m3_s"] == pytest.approx(180 / 3600)
        assert v["fan_power_w"] <= p["fan_power_w"]
    with pytest.raises(ValueError):
        control_step("vav", 1, c)


def test_ductless():
    import yaml

    d = yaml.safe_load((ROOT / "cases/book/ch04/ex4-11.yaml").read_text())["input"]
    r = ductless(d)
    assert r["demand_m3_s"] * 3600 == pytest.approx(60)
    assert [x["effective_flow_m3_s"] * 3600 for x in r["results"]] == pytest.approx([64, 56])
    assert [x["satisfied"] for x in r["results"]] == [True, False]
    assert r["outlet_check"]["short_circuit_warning"]
    d["devices"] = 2
    assert not ductless(d)["one_unit_recommended"]
    d["effectiveness"] = [1.1]
    with pytest.raises(ValueError):
        ductless(d)


def test_legacy_case_alias_warns():
    import yaml

    from openresivent.core.case import Case
    from openresivent.core.runner import execute

    value = yaml.safe_load((ROOT / "cases/book/ch04/ex4-11.yaml").read_text())
    original = Case.model_validate(value)
    expected, _ = execute(original, ROOT / "cases/book/ch04/ex4-11.yaml")
    value["module"] = "p" + "303_ductless"
    with pytest.warns(FutureWarning):
        old = Case.model_validate(value)
    assert old.module == "ductless"
    actual, _ = execute(old, ROOT / "cases/book/ch04/ex4-11.yaml")
    assert actual == expected


@pytest.mark.parametrize("ident", ["ex4-02", "ex4-07", "ex4-11"])
def test_cli(ident, tmp_path):
    if ident in ("ex4-02", "ex4-07") and not os.environ.get("ORV_WEATHER_DIR"):
        pytest.skip("未配置广州 EPW")
    c = ROOT / "cases/book/ch04" / f"{ident}.yaml"
    r = CliRunner().invoke(app, ["run", str(c), "--out", str(tmp_path)])
    assert r.exit_code == 0, r.exception
    data = json.loads((tmp_path / f"{ident}.json").read_text())
    text = (tmp_path / f"{ident}.md").read_text()
    assert "敏感性说明" in text and len(data["provenance"]["input_sha256"]) == 64
    assert not re.search(r"合成禁词|(?:GBT|JGJT|GB)\d{3,}-\d{4}:", text)
    if ident == "ex4-07":
        assert data["free_cooling_hours"] > 0 and data["bypass_extra_free_cooling_j"] > 0
        assert data["provenance"]["data_sha256"]["guangzhou.epw"]
