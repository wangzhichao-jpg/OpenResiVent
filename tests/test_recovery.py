"""M4 积尘、结霜、选型及运维。"""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from openresivent.energy.model import AnnualConfig, ControlConfig, annual
from openresivent.energy.weather import WeatherHour
from openresivent.recovery.fouling import (
    bounded_exchanger,
    collected_dust,
    dust_for_resistance_ratio,
    exchanger_regression,
    mass_balance_period,
    replacement_period,
    snapshot,
    sun_dynamic_doubling,
    sun_dynamic_period,
    sun_figure_flow,
)
from openresivent.recovery.frost import (
    cold_corner,
    figure10_threshold,
    figure11_threshold,
    strategies,
)
from openresivent.recovery.selection import assess, maintenance

TARGETS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "cases/benchmarks/targets.yaml").read_text(
        encoding="utf8"
    )
)


def test_dust_and_replacement():
    assert dust_for_resistance_ratio(2, "lyu") * 1000 == pytest.approx(
        TARGETS["P204_A06_A07"]["values"][0], rel=1e-6
    )
    assert dust_for_resistance_ratio(2, "sun") * 1000 == pytest.approx(
        TARGETS["P204_A06_A07"]["values"][1], rel=1e-6
    )
    assert replacement_period(90e-9, 1, 180 / 3600, model="lyu") / 86400 == pytest.approx(
        TARGETS["P204_A08"]["value"], rel=1e-6
    )
    assert collected_dust(0.09e-6, 0.8, 180 / 3600, 1000 * 3600) * 1000 == pytest.approx(
        TARGETS["P204_A10"]["value"], rel=1e-9
    )
    with pytest.raises(ValueError):
        replacement_period(0, 1, 0.1)
    with pytest.raises(ValueError):
        dust_for_resistance_ratio(0.5)


@pytest.mark.parametrize(("concentration", "published_days"), [(90, 49), (20, 218)])
def test_published_mass_balance_endpoints(concentration, published_days):
    result = mass_balance_period(0.0342, concentration * 1e-9, 323.75 / 3600)
    assert result["period_s"] / 86400 == pytest.approx(published_days, rel=0.05)
    assert result["particulate"] == "PM10"


def test_mass_balance_particulate_and_boundaries():
    pm25 = mass_balance_period(0.0342, 45e-9, 323.75 / 3600, particulate="PM2.5")
    assert pm25["period_s"] / 86400 == pytest.approx(97.8120978, rel=1e-6)
    baseline = mass_balance_period(0.0342, 65e-9, 323.75 / 3600)["period_s"]
    assert baseline / 86400 == pytest.approx(67.716, rel=0.001)
    assert mass_balance_period(0.0342, 65e-9, 323.75 / 3600, duty_fraction=0.5)[
        "period_s"
    ] == pytest.approx(baseline * 2)
    for kwargs in (
        {"mass": 0},
        {"concentration": float("nan")},
        {"mean_flow": 0},
        {"duty_fraction": 1.1},
        {"capture_efficiency": 0},
        {"particulate": "PM1"},
    ):
        args = {"mass": 0.0342, "concentration": 45e-9, "mean_flow": 0.1}
        args.update(kwargs)
        with pytest.raises(ValueError):
            mass_balance_period(**args)


def test_paper2_dynamic_reading():
    x = sun_dynamic_doubling()
    assert sun_dynamic_period(90e-9, 1) / 86400 == pytest.approx(50.56152, rel=1e-5)
    assert x["dirty"]["filter_pressure_pa"] == pytest.approx(
        2 * x["clean"]["filter_pressure_pa"], rel=1e-9
    )
    assert 0.75 < x["flow_ratio"] < 0.9
    with pytest.raises(ValueError):
        sun_figure_flow(-1)
    with pytest.raises(ValueError):
        sun_figure_flow(0.3)
    cfg = replace(
        ControlConfig(), design_flow=350 / 3600, filter_model="sun", fan_model="sun_digitized"
    )
    weather = [WeatherHour(1, 1, 1, 273.15, 0.002)] * 2
    result = annual(
        weather,
        lambda _: "heating",
        config=replace(AnnualConfig(), control=cfg),
        mode="cav",
        recovery_model=exchanger_regression,
        exhaust_flow=350 / 3600,
        filter_replacement_ratio=2,
    )
    assert result["annual"]["hours"] == 2


def test_regression_and_m5_coupling():
    boundary = bounded_exchanger(238.15, 294.15, 0.001, 0.0059, 300 / 3600, 350 / 3600)
    assert boundary["within_physical_range"] and boundary["bounded_extrapolation"]
    c = exchanger_regression(273.15, 293.15, 0.002, 0.007, 350 / 3600, 350 / 3600)
    assert c["within_physical_range"] and c["within_flow_validation_range"]
    low = snapshot(
        0.02,
        273.15,
        293.15,
        0.002,
        0.007,
        350 / 3600,
        ControlConfig(design_flow=350 / 3600, filter_model="sun"),
    )
    assert low["supply_m3_s"] > 0 and low["infiltration_m3_s"] >= 0
    weather = [WeatherHour(1, 1, 1, 273.15, 0.002)] * 24
    cfg = replace(AnnualConfig(), flow=300 / 3600)
    result = annual(
        weather,
        lambda _: "heating",
        config=cfg,
        recovery_model=exchanger_regression,
        exhaust_flow=350 / 3600,
    )
    assert result["annual"]["infiltration_j"] > 0
    assert result["annual"]["ventilation_j"] > result["annual"]["infiltration_j"]


def test_frost_and_strategy():
    assert figure10_threshold(259.15, 0.5) * 3600 == pytest.approx(170)
    assert figure10_threshold(243.15, 0.6) * 3600 == pytest.approx(49)
    assert figure11_threshold(259.15, 0.77) * 3600 == pytest.approx(63.6)
    with pytest.raises(ValueError):
        figure11_threshold(273.15, 0.5)
    with pytest.raises(ValueError):
        figure10_threshold(263.15, 0.5)
    # 仅检验判据计算和边界，参数为自拟，非论文标定值。
    x = cold_corner(259.15, 293.15, 0.001, 0.007, 200 / 3600, 15, 15, 0.01, 0.01)
    assert isinstance(x["frost_risk"], bool)
    z = strategies(259.15, 293.15, 400 / 3600, 170 / 3600, 0.75)
    assert z["preheat"]["electric_w"] > 0
    assert z["reduce_flow"]["supply_m3_s"] == pytest.approx(170 / 3600)
    assert z["bypass"]["available_recovery_w"] == 0
    assert z["preheat"]["electric_j"] == pytest.approx(z["preheat"]["electric_w"] * 3600)
    assert z["bypass"]["recovery_loss_fraction"] == 1


def test_selection_and_maintenance():
    n = assess(
        "near_zero",
        sensible_heat=0.74,
        sensible_cool=0.70,
        total_heat=0.71,
        total_cool=0.6,
        specific_power=0.46 * 3600,
    )
    assert not n["passed"] and not n["checks"][0]["passed"] and not n["checks"][-1]["passed"]
    g = assess(
        "general",
        equipment_type="total",
        sensible_heat=0.71,
        sensible_cool=0.66,
        total_heat=0.61,
        total_cool=0.56,
        specific_power=0.5 * 3600,
    )
    assert g["passed"]
    assert maintenance("cellulose", initial_latent=0.8, after_clean_latent=0.63)[
        "replace_recommended"
    ]
    assert not maintenance("paper", initial_latent=0.8, after_clean_latent=0.7)[
        "replace_recommended"
    ]
    with pytest.raises(ValueError):
        maintenance("bad", initial_latent=0.8, after_clean_latent=0.7)
    with pytest.raises(ValueError):
        assess(
            "bad",
            sensible_heat=0.7,
            sensible_cool=0.7,
            total_heat=0.7,
            total_cool=0.7,
            specific_power=1,
        )
