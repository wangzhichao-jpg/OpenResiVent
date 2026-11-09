"""多区 M7 联合工况测试。"""

import pytest

from openresivent.dwelling.templates import Dwelling, acceptance_scenarios, calculate


@pytest.mark.parametrize("bedrooms", [2, 3, 4])
@pytest.mark.parametrize("open_kitchen", [True, False])
def test_templates(bedrooms, open_kitchen):
    home = Dwelling(bedrooms, kitchen_open=open_kitchen)
    baseline = calculate(home)
    x = calculate(
        home,
        hood=300 / 3600,
        fresh_supply=150 / 3600,
        fresh_exhaust=127.5 / 3600,
        bath_exhaust=90 / 3600,
    )
    makeup = calculate(
        home,
        hood=300 / 3600,
        fresh_supply=150 / 3600,
        fresh_exhaust=127.5 / 3600,
        bath_exhaust=90 / 3600,
        opening_area=0.02,
    )
    locked = calculate(
        home,
        hood=300 / 3600,
        fresh_supply=150 / 3600,
        fresh_exhaust=127.5 / 3600,
        interlock="stop_exhaust",
    )
    assert len(x["acceptance_scenarios"]) == 3
    assert max(abs(p) for p in baseline["pressures_pa"].values()) < 1e-7
    assert x["mass_residual_kg_s"] < 1e-10
    assert makeup["opening_m3_s"] > 0
    assert makeup["pressures_pa"][x["gas_zone"]] > x["pressures_pa"][x["gas_zone"]]
    assert locked["fresh_exhaust_m3_s"] == 0
    assert locked["normal_exhaust_supply_ratio"] == pytest.approx(0.85)
    assert locked["normal_ratio_80_90"] is True
    assert baseline["normal_ratio_80_90"] is None
    assert len(x["doors"]) == len(x["pressures_pa"]) - 1


@pytest.mark.parametrize("bedrooms", [2, 3, 4])
@pytest.mark.parametrize("scenario", acceptance_scenarios(), ids=lambda x: x["name"])
def test_acceptance_scenarios_end_to_end(bedrooms, scenario):
    x = calculate(
        Dwelling(bedrooms),
        hood=(300 / 3600 if scenario["hood"] else 0),
        fresh_supply=(150 / 3600 if scenario["ventilation"] else 0),
        fresh_exhaust=(127.5 / 3600 if scenario["ventilation"] else 0),
        bath_exhaust=(90 / 3600 if scenario["bath_fan"] else 0),
    )
    assert x["mass_residual_kg_s"] < 1e-10
    assert all(
        k in x
        for k in (
            "pressures_pa",
            "doors",
            "fresh_supply_m3_s",
            "fresh_exhaust_m3_s",
            "opening_m3_s",
            "entrance_opening_force_n",
            "acceptance_scenarios",
        )
    )
    assert x["fresh_supply_m3_s"] == pytest.approx(150 / 3600 if scenario["ventilation"] else 0)
    assert "hood" in x["flows"] if scenario["hood"] else "hood" not in x["flows"]
    assert scenario["measure"] and scenario in x["acceptance_scenarios"]


def test_validation_and_increased_supply():
    with pytest.raises(ValueError):
        calculate(Dwelling(1))
    with pytest.raises(ValueError):
        calculate(Dwelling(2), interlock="bad")
    with pytest.raises(ValueError):
        calculate(Dwelling(2), hood=-1)
    x = calculate(
        Dwelling(2), hood=300 / 3600, fresh_supply=150 / 3600, interlock="increase_supply"
    )
    assert x["fresh_supply_m3_s"] == pytest.approx(450 / 3600)
