"""倍频程风管噪声、解析基准和反算。"""

import copy
import math
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from openresivent.api import app as api
from openresivent.cli import app
from openresivent.duct.noise import (
    a_weight,
    calculate_noise,
    noise_case,
    room_pressure,
    room_pressure_thompson,
    sum_levels,
)

ROOT = Path(__file__).resolve().parents[1]


def data():
    return yaml.safe_load((ROOT / "cases/book/ch04/ex4-09.yaml").read_text())["input"]


def test_published_room_examples():
    # Engineering ToolBox, Propagation of Sound Indoors, Example – Received Sound.
    assert room_pressure(90, 1, 2, 15.3) == pytest.approx(84.8, abs=0.5)
    # Nexora, Fan sound power to room sound pressure, section 4, 1000 Hz.
    assert room_pressure(46.12, 2, 3, 80) == pytest.approx(34.43, abs=0.5)


def test_published_handbook_thompson_example():
    # HVAC Acoustic Fundamentals，AG 31-010，第35页，63 Hz，5 ft。
    result = room_pressure_thompson(34, 2, 5 * 0.3048, 313 * 0.09290304, 7.7 * 0.3048)
    target = yaml.safe_load((ROOT / "cases/benchmarks/targets.yaml").read_text())[
        "noise_room_thompson"
    ]
    assert result == pytest.approx(target["value_db"], abs=target["tolerance_db"])
    with pytest.raises(ValueError):
        room_pressure_thompson(34, 2, 0, 1, 1)


def test_public_analytic_benchmarks():
    # HVAC Acoustic Fundamentals AG 31-010, p.6：双声源 +3 dB 与 5 声源 94 dB。
    targets = yaml.safe_load((ROOT / "cases/benchmarks/targets.yaml").read_text())[
        "noise_energy_benchmarks"
    ]
    for item in targets:
        assert sum_levels([v + a_weight(1000) for v in item["levels_db"]]) == pytest.approx(
            item["value_db"], abs=1
        )
    assert a_weight(1000) == pytest.approx(0, abs=0.01)
    expected = 70 + 10 * math.log10(2 / (4 * math.pi * 2**2) + 4 / 20)
    assert room_pressure(70, 2, 2, 20) == pytest.approx(expected)


def test_published_two_db_duct_loss():
    # HVAC Systems Noise Control，风管衬里示例：125 Hz 衰减 2 dB。
    d = data()
    d["stages"] = [{"kind": "straight", "attenuation_db": [0, 2, 0, 0, 0, 0, 0, 0]}]
    d["terminal_reflection_db"] = [0] * 8
    d.pop("diffuser_regenerated_db")
    result = calculate_noise(d, d["reference_flow_m3_s"])
    assert result["terminal_power_db"][1] == pytest.approx(d["fan_power_db"][1] - 2, abs=1e-12)


def test_octave_path_and_inverse():
    d = data()
    r = noise_case(d)
    assert len(r["settings"][0]["room_pressure_db"]) == 8
    levels = [x["a_weighted_db"] for x in r["settings"]]
    assert levels == sorted(levels) and len(set(levels)) == len(levels)
    assert calculate_noise(d, r["maximum_flow_m3_s"])["a_weighted_db"] == pytest.approx(33, abs=0.1)
    assert r["maximum_flow_m3_s"] * 3600 == pytest.approx(77.7756, abs=0.01)
    changed = copy.deepcopy(d)
    changed["stages"][0]["attenuation_db"] = [x + 3 for x in changed["stages"][0]["attenuation_db"]]
    assert (
        calculate_noise(changed, d["reference_flow_m3_s"])["a_weighted_db"]
        < calculate_noise(d, d["reference_flow_m3_s"])["a_weighted_db"]
    )


def test_fan_estimate_and_rejections():
    d = data()
    del d["fan_power_db"]
    d.update(fan_pressure_pa=100, fan_specific_level_db=40, fan_octave_offsets_db=[-10] * 8)
    assert math.isfinite(calculate_noise(d, d["reference_flow_m3_s"])["a_weighted_db"])
    from openresivent.report.noise import render_noise

    r = noise_case(d)
    r["checks"] = [{"passed": True} for _ in r["settings"]]
    assert "由风机比声功率和频谱偏移估算" in render_noise(d, r)
    with pytest.raises(ValueError):
        a_weight(0)
    with pytest.raises(ValueError):
        sum_levels([])
    with pytest.raises(ValueError):
        room_pressure(60, 0, 1, 10)
    d["terminal_reflection_db"] = [1]
    with pytest.raises(ValueError):
        calculate_noise(d, 0.01)


def test_noise_case_cli_and_optional_api(tmp_path):
    case = ROOT / "cases/book/ch04/ex4-09.yaml"
    outcome = CliRunner().invoke(app, ["run", str(case), "--out", str(tmp_path)])
    assert outcome.exit_code == 0, outcome.exception
    text = (tmp_path / "ex4-09.md").read_text()
    assert all(x in text for x in ("**已知条件**", "**计算**", "**结果**", "**条文对照**"))
    assert "| 参考风量 | $Q_0$ | 100 | m³/h |" in text
    assert "直管1倍频程衰减" in text and "风口再生声功率" in text
    payload = yaml.safe_load((ROOT / "cases/book/ch02/ex2-03.yaml").read_text())
    payload["input"]["noise"] = data()
    response = TestClient(api).post("/run", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["noise"]["at_maximum_db"] == pytest.approx(33, abs=0.1)
    assert response.json()["noise"]["checks"][0]["limit"] == 33
