"""厨房本地补风与连续通风默认位置。"""

from pathlib import Path

import pytest
import yaml

from openresivent.core.p2_examples import run_dwelling
from openresivent.dwelling.templates import Dwelling, calculate
from openresivent.report.book import render_book
from openresivent.report.markdown import render

ROOT = Path(__file__).resolve().parents[1]


def test_defaults_and_location_warning():
    home = Dwelling(3)
    default = calculate(
        home,
        hood=300 / 3600,
        fresh_supply=150 / 3600,
        opening_area=0.02,
        mechanical_makeup=10 / 3600,
    )
    assert default["device_rooms"]["opening"] == "kitchen"
    assert default["device_rooms"]["makeup"] == "kitchen"
    assert default["device_rooms"]["fresh_supply"] == ["living", "bed1"]
    assert default["device_rooms"]["fresh_exhaust"] == "bath"
    assert default["makeup_location_warning"] is None
    other = calculate(home, hood=300 / 3600, opening_area=0.02, opening_room="living")
    assert other["makeup_location_warning"] == "补风口宜设在厨房本地"


def test_counterexample_and_values():
    data = yaml.safe_load((ROOT / "cases/book/ch05/ex5-07.yaml").read_text())["input"]
    result = run_dwelling(data)
    for n in ("1.0", "0.6"):
        scenarios = result["scenarios"][n]
        assert scenarios["opening_kitchen"]["pressures_pa"]["kitchen"] >= -15
        assert scenarios["opening"]["pressures_pa"]["kitchen"] < -15
    assert result["scenarios"]["1.0"]["opening"]["pressures_pa"]["kitchen"] == pytest.approx(
        -32.654, abs=0.002
    )
    assert result["scenarios"]["1.0"]["mechanical_kitchen"]["pressures_pa"][
        "kitchen"
    ] == pytest.approx(-21.514, abs=0.002)
    text = render_book(
        "户内压差", "ex5-07", "ch05", render("户内压差", "dwelling_pressure", data, result), result
    )
    assert "反例：补风口不在厨房" in text and "厨房机械补风方案" in text
