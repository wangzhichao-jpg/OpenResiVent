"""补风反算、阈值和已满足边界。"""

import pytest

from openresivent.dwelling.makeup import minimum_makeup
from openresivent.dwelling.templates import Dwelling, calculate


@pytest.mark.parametrize("n50", [1.0, 0.6])
@pytest.mark.parametrize("mode", ["mechanical", "opening"])
def test_inverted_threshold(n50, mode):
    home = Dwelling(3, n50=n50 / 3600)
    args = {
        "hood": 300 / 3600,
        "fresh_supply": 150 / 3600,
        "fresh_exhaust": 127.5 / 3600,
        "supply_room": "living",
    }
    result = minimum_makeup(home, mode=mode, **args)
    field = "mechanical_makeup" if mode == "mechanical" else "opening_area"
    forward = calculate(home, **args, **{field: result["value"]})
    assert forward["pressures_pa"][forward["gas_zone"]] == pytest.approx(-15, abs=0.01)
    assert result["tolerance_pa"] == 0.01 and result["value"] > 0
    reduced = calculate(home, **args, **{field: result["value"] * 0.99})
    assert reduced["pressures_pa"][reduced["gas_zone"]] < -15


def test_already_satisfied_and_validation():
    home = Dwelling(2)
    assert minimum_makeup(home, mode="opening")["value"] == 0
    with pytest.raises(ValueError):
        minimum_makeup(home, mode="bad")
    with pytest.raises(ValueError):
        minimum_makeup(home, mode="opening", opening_area=0.1)
