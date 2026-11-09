"""标准测试数据处理及边界测试。"""

from datetime import datetime, timedelta

import pytest

from openresivent.core.case import Case
from openresivent.core.runner import execute
from openresivent.measure.acceptance import (
    continuous_monitor,
    design_window_judgement,
    flow_deviation,
    required_homes,
    spot_evaluate,
    spot_monitor,
    track_judgement,
)


def test_flow_and_sample_counts():
    assert flow_deviation(200, 185)["passed"]
    assert flow_deviation(200, 185)["deviation"] == pytest.approx(-0.075)
    assert not flow_deviation(50, 60, terminal=True)["passed"]
    assert required_homes(1) == 1
    assert required_homes(21) == 2
    with pytest.raises(ValueError):
        flow_deviation(0, 1)
    with pytest.raises(ValueError):
        required_homes(0)


def test_monitor_worst_five_days():
    start = datetime(2026, 1, 1)
    records = []
    for i in range(30 * 144):
        day = i // 144
        records.append(
            {
                "time": (start + timedelta(minutes=10 * i)).isoformat(),
                "outdoor_pm": (100 if day >= 25 else 20) * 1e-9,
                "indoor_pm": (day + 10) * 1e-9,
                "indoor_co2": 0.0008,
            }
        )
    result = continuous_monitor(records)
    assert result["selected_days"] == [f"2026-01-{d:02}" for d in range(26, 31)]
    assert result["indoor_pm"] == pytest.approx(37e-9)
    design = design_window_judgement(records)
    assert design["pm25_passed"] and design["co2_passed"]
    assert design["co2_max_1h"] == pytest.approx(0.0008)
    with pytest.raises(ValueError):
        design_window_judgement(records[:10])
    with pytest.raises(ValueError):
        design_window_judgement(records[:145:2])
    assert track_judgement(result["indoor_pm"], result["indoor_co2"])["design"]["pm25_passed"]
    with pytest.raises(ValueError):
        continuous_monitor(records[:20])
    with pytest.raises(ValueError):
        continuous_monitor(records[:1])
    with pytest.raises(ValueError):
        track_judgement(-1, 0)


def test_actual_acceptance_dispatch(tmp_path):
    start = datetime(2026, 1, 1)
    records = [
        {
            "time": (start + timedelta(minutes=i * 10)).isoformat(),
            "outdoor_pm_ug_m3": 100 if i // 144 >= 25 else 20,
            "indoor_pm_ug_m3": 40,
            "indoor_co2_ppm": 800,
        }
        for i in range(30 * 144)
    ]
    spot = [
        {
            "time": (start + timedelta(minutes=i)).isoformat(),
            "indoor_pm_ug_m3": 40,
            "indoor_co2_ppm": 800,
        }
        for i in range(46)
    ]
    case = Case.model_validate(
        {
            "meta": {"id": "test", "title": "测试"},
            "module": "acceptance",
            "input": {
                "records": records,
                "spot_records": spot,
                "total_design_m3_h": 200,
                "total_measured_m3_h": 185,
                "terminal_design_m3_h": 50,
                "terminal_measured_m3_h": 60,
                "total_homes": 21,
            },
        }
    )
    out, versions = execute(case, tmp_path / "case.yaml")
    assert out["tracks"]["design"]["pm25_max_24h"] == pytest.approx(40e-9)
    assert out["spot"]["status"] == "passed"
    assert out["required_homes"] == 2
    assert versions["JGJT440-2018"] == "2018"


def test_spot_retest():
    start = datetime(2026, 1, 1)

    def rows(minutes, pm):
        return [
            {
                "time": (start + timedelta(minutes=i)).isoformat(),
                "indoor_pm": pm,
                "indoor_co2": 0.0008,
            }
            for i in range(minutes + 1)
        ]

    assert spot_evaluate(rows(44, 30e-9))["status"] == "invalid_first"
    assert spot_evaluate(rows(45, 30e-9))["status"] == "passed"
    assert spot_evaluate(rows(45, 100e-9))["status"] == "retest_required"
    assert (
        spot_evaluate(rows(45, 100e-9), retest_records=rows(1079, 30e-9))["status"]
        == "invalid_retest"
    )
    assert spot_evaluate(rows(45, 100e-9), retest_records=rows(1080, 30e-9))["status"] == "passed"
    assert spot_evaluate(rows(45, 100e-9), retest_records=rows(1080, 100e-9))["status"] == "failed"


def test_spot():
    start = datetime(2026, 1, 1)
    times = [start + timedelta(minutes=i) for i in range(46)]
    assert spot_monitor(times)["duration_passed"]
    assert not spot_monitor(times, retest=True)["duration_passed"]
    assert not spot_monitor([start, start + timedelta(minutes=2)])["recommended_one_minute"]
    with pytest.raises(ValueError):
        spot_monitor([start])
    with pytest.raises(ValueError):
        spot_monitor([start, start])
