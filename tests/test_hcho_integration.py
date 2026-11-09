"""甲醛路径集成及单位边界。"""

from pathlib import Path

import pytest

from openresivent.core.case import load_case
from openresivent.core.runner import execute
from openresivent.ventrate.calculation import Room, calculate_dwelling

ROOT = Path(__file__).resolve().parents[1]


def test_room_hcho_drives_design():
    r = calculate_dwelling(
        30,
        2.8,
        1,
        [Room(10, 2.8, 1, hcho_generation=1.2e-6 / 3600)],
        Room(10, 2.8, 1),
        hcho_outdoor=0.01e-6,
    )
    assert r["bedrooms"][0]["D"] * 3600 == pytest.approx(1.2 / 0.07)
    assert r["bedrooms"][0]["selected"] >= r["bedrooms"][0]["D"]
    assert r["design"] >= r["only_440"]
    with pytest.raises(ValueError):
        calculate_dwelling(
            30, 2.8, 1, [Room(10, 2.8, 1)], Room(10, 2.8, 1), hcho_whole_generation=-1
        )


def test_input_material_units():
    path = ROOT / "cases/book/ch02/ex2-03.yaml"
    case = load_case(path)
    case.input["bedrooms"][0]["hcho_materials"] = [{"ef_mg_m2_h": 0.12, "area_m2": 10}]
    out, _ = execute(case, path)
    assert out["bedrooms"][0]["D"] * 3600 == pytest.approx(1.2 / 0.07)
