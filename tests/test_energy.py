"""M5 能量平衡、逐时气象和控制基准。"""

import os
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from openresivent.core.psychrometrics import enthalpy
from openresivent.energy.model import (
    AnnualConfig,
    ControlConfig,
    annual,
    control_step,
    enthalpy_power,
    fan_curve_operating_point,
    fan_power,
    filter_pressure,
    hourly_load,
    paper_erv_efficiencies,
    paper_heat_pump_cop,
    saving_ratio,
    sensible_power,
    sun_filter_pressure,
)
from openresivent.energy.seasons import city_season
from openresivent.energy.weather import WeatherHour, read_epw

TARGETS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "cases/benchmarks/targets.yaml").read_text(
        encoding="utf8"
    )
)


def test_heat_cool_and_bypass():
    q = 150 / 3600
    assert sensible_power(q, 1.2, 1006, 20) == pytest.approx(
        TARGETS["P203_A06"]["values"][0], rel=1e-9
    )
    assert sensible_power(q, 1.2, 1006, 20, 0.75) == pytest.approx(
        TARGETS["P203_A06"]["values"][1], rel=1e-9
    )
    dh = (enthalpy(308.15, 0.020) - enthalpy(299.15, 0.0105)) / 1000
    assert dh == pytest.approx(TARGETS["P203_A07"]["values"][0], rel=1e-6)
    assert enthalpy_power(q, 1.2, 308.15, 0.020, 299.15, 0.0105) == pytest.approx(
        TARGETS["P203_A07"]["values"][1], rel=1e-6
    )
    assert enthalpy_power(q, 1.2, 308.15, 0.020, 299.15, 0.0105, 0.6) == pytest.approx(
        TARGETS["P203_A07"]["values"][2], rel=1e-6
    )
    x = hourly_load(
        WeatherHour(7, 1, 1, 295.15, 0.009),
        mode="cooling",
        indoor_temperature=297.15,
        indoor_ratio=0.01,
        flow=q,
        sensible_efficiency=0.75,
        enthalpy_efficiency=0.6,
        bypass="temperature",
    )
    assert x["bypass"] and x["recovered_w"] == 0
    assert x["natural_cooling_w"] == pytest.approx(TARGETS["P203_A10"]["value"])
    assert fan_power(q, 0.45 * 3600) == pytest.approx(67.5)
    assert paper_erv_efficiencies(280 / 3600, "heating") == pytest.approx((0.801, 0.737))
    assert paper_heat_pump_cop(273.15, "heating") == pytest.approx(2.522)
    with pytest.raises(ValueError):
        paper_erv_efficiencies(-1, "heating")
    with pytest.raises(ValueError):
        paper_heat_pump_cop(273.15, "bad")
    cold = WeatherHour(1, 1, 1, 273.15, 0.001)
    frozen = hourly_load(
        cold,
        mode="heating",
        indoor_temperature=293.15,
        indoor_ratio=0.006,
        flow=q,
        sensible_efficiency=0.75,
        frost=lambda _: True,
    )
    assert frozen["frost_disabled"] and frozen["heating_w"] == pytest.approx(1006)


def test_constant_annual():
    weather = [WeatherHour(1, 1, 1, 273.15, 0.002)] * 8760
    config = AnnualConfig(sensible_efficiency=0)
    base = annual(weather, lambda w: "heating", config=config)
    other = annual(weather, lambda w: "heating", config=replace(config, sensible_efficiency=0.75))
    assert base["annual"]["ventilation_j"] / 3.6e6 == pytest.approx(
        TARGETS["P203_A08"]["values"][0], rel=1e-9
    )
    assert other["annual"]["ventilation_j"] / 3.6e6 == pytest.approx(
        TARGETS["P203_A08"]["values"][1], rel=1e-9
    )
    assert base["annual"]["fan_j"] / 3.6e6 == pytest.approx(TARGETS["P203_A09"]["value"], rel=1e-9)
    assert 0 < saving_ratio(base, other) < 1


def test_filter_control_and_seasons():
    from openresivent.network.elements import PolynomialFan

    op = fan_curve_operating_point(
        PolynomialFan((200, 0, -200 / (400 / 3600) ** 2), 400 / 3600),
        lambda q: 200 * (q / (400 / 3600)) ** 2,
        0.5,
    )
    assert op["flow_m3_s"] * 3600 == pytest.approx(400 / 2**0.5)
    assert sun_filter_pressure(280 / 3600, 0.01) == pytest.approx(
        0.018283 * 280**1.395292 * 1.026994**10
    )
    assert control_step("cav", 0.01, replace(ControlConfig(), filter_model="sun"))["flow_m3_s"] > 0
    assert sun_filter_pressure(280 / 3600, 0.01, 0.0199, 1.3809, 1.0269) == pytest.approx(
        filter_pressure(280 / 3600, 0.01)
    )
    with pytest.raises(ValueError):
        sun_filter_pressure(1, 0, 1, 1, 0.5)
    assert filter_pressure(280 / 3600, 0.01) == pytest.approx(0.0199 * 280**1.3809 * 1.0269**10)
    c = ControlConfig()
    cav = control_step("cav", 0, c)
    pid = control_step("pid", 0, c)
    vav = control_step("vav", 0, c)
    assert cav["flow_m3_s"] > c.design_flow
    assert pid["flow_m3_s"] == pytest.approx(c.design_flow)
    assert pid["valve_pressure_pa"] >= c.pid_min_pressure
    assert vav["flow_m3_s"] == pytest.approx(c.design_flow)
    assert control_step("cav", 0.03, c)["flow_m3_s"] < cav["flow_m3_s"]
    assert control_step("pid", 0.1, c)["flow_m3_s"] < c.design_flow
    for city in ("harbin", "beijing", "shanghai", "guangzhou"):
        assert city_season(city, WeatherHour(7, 1, 1, 300, 0.01)) in ("cooling", "off")
    with pytest.raises(ValueError):
        city_season("unknown", WeatherHour(1, 1, 1, 290, 0.01))
    with pytest.raises(ValueError):
        control_step("wrong", 0)
    with pytest.raises(ValueError):
        filter_pressure(-1, 0)


def test_epw_synthetic(tmp_path):
    p = tmp_path / "x.epw"
    p.write_text(("header\n" * 8) + "2020,1,1,1,60,X,0,-3,80,101325\n", encoding="utf8")
    assert read_epw(p, require_year=False)[0].temperature == pytest.approx(273.15)
    with pytest.raises(ValueError):
        read_epw(p)
    p.write_text(("header\n" * 8) + "2020,1,1,1,60,X,99.9,-3,80,101325\n", encoding="utf8")
    with pytest.raises(ValueError):
        read_epw(p, require_year=False)
    p.write_text(("header\n" * 8) + ("2020,1,1,1,60,X,0,-3,80,101325\n" * 8760), encoding="utf8")
    with pytest.raises(ValueError, match="缺失、重复或乱序"):
        read_epw(p)


@pytest.mark.parametrize("city", ["harbin", "beijing", "shanghai", "guangzhou"])
def test_external_epw(city):
    folder = os.environ.get("ORV_WEATHER_DIR")
    if not folder:
        pytest.skip("未配置 ORV_WEATHER_DIR，跳过真实 TMYx 气象")
    rows = read_epw(Path(folder) / (city + ".epw"))
    assert len(rows) == 8760
