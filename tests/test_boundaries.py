"""边界条件和网络错误处理。"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.core.psychrometrics import (
    dew_point,
    enthalpy,
    humidity_ratio,
    saturation_pressure,
)
from openresivent.network.solver import Zone, solve
from openresivent.rules.engine import check_rule, load_pack
from openresivent.ventrate.calculation import air_changes_rate

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("area", "expected"),
    [(10, 0.7), (10.00001, 0.6), (20, 0.6), (20.00001, 0.5), (50, 0.5), (50.00001, 0.45)],
)
def test_tiers(area, expected):
    assert air_changes_rate(area) * 3600 == pytest.approx(expected)


def test_disconnected_network():
    with pytest.raises(ValueError, match="未连接"):
        solve({"outside": Zone(293, fixed=True), "isolated": Zone(293)}, [])


def test_rule_needs_computed_limit():
    pack = load_pack(ROOT / "src/openresivent/rules/packs/jgj440_2018.yaml")
    rule = next(x for x in pack["rules"] if x["id"].endswith("4.2.3"))
    with pytest.raises(ValueError):
        check_rule(rule, 1)
    assert not check_rule(rule, 1, calculated_limit=2)["passed"]


def test_hyland_wexler_triple_point():
    # IAPWS R7-97(2012), 273.16 K 三相点饱和压力 611.657 Pa。
    assert saturation_pressure(273.16) == pytest.approx(611.657, rel=0.001)


def test_psychrolib_reference_dewpoint():
    # PsychroLib 官方文档的 ASHRAE Fundamentals 2017 第1章示例：25 °C、80% RH。
    # https://psychrometrics.github.io/psychrolib/api_docs.html
    assert dew_point(298.15, 0.8) - 273.15 == pytest.approx(21.309397163661785, rel=0.001)


def test_published_25c_example():
    # 公开示例：25 °C、50% RH、101.325 kPa；数值已被来源四舍五入。
    # https://www.firgelliauto.com/blogs/engineering-calculators/psychrometric-calculator
    w = humidity_ratio(298.15, 0.5, 101325)
    assert saturation_pressure(298.15) == pytest.approx(3169, abs=0.5)
    assert w == pytest.approx(0.00988, abs=0.000005)
    assert enthalpy(298.15, w) == pytest.approx(50300, abs=50)


@pytest.mark.parametrize("case", ["ch03/ex3-01.yaml", "ch05/ex5-01.yaml"])
def test_network_cli(tmp_path, case):
    result = CliRunner().invoke(
        app, ["run", str(ROOT / "cases/book" / case), "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.exception
