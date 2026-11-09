"""规则包及人员法开关的验证。"""

from pathlib import Path

import pytest

from openresivent.core.case import Case, load_case
from openresivent.core.runner import execute, load_activity, load_rules
from openresivent.rules.engine import check_rule

ROOT = Path(__file__).resolve().parents[1]


def test_activity_table_drives_input():
    table = load_activity()
    assert table["sedentary"] * 3600 * 1000 == pytest.approx(18)
    assert 9 < table["sleeping"] * 3600 * 1000 < 13
    assert table["moderate_activity"] > table["light_housework"] > table["sleeping"]
    assert load_activity({"sex": "female"})["light_housework"] < table["light_housework"]
    assert load_activity({"weight_kg": 80})["sleeping"] > table["sleeping"]


def test_people_rule_switch():
    path = ROOT / "cases/book/ch02/ex2-03.yaml"
    case = load_case(path)
    combined, versions = execute(case, path)
    case_only = Case.model_validate(
        {**case.model_dump(), "meta": {**case.meta.model_dump(), "rules": ["JGJT440-2018"]}}
    )
    only, _ = execute(case_only, path)
    assert combined["design"] >= only["design"]
    assert only["design"] == pytest.approx(combined["only_440"])
    assert "GBT18883-2022" in versions
    assert any(x["id"].startswith("GBT18883") for x in combined["checks"])
    assert not any(x["id"].startswith("GBT18883") for x in only["checks"])


def test_pack_thresholds():
    rules, versions = load_rules(["JGJT440-2018", "GBT18883-2022", "GBT51350-2019", "GB50736-2012"])
    assert len(versions) == 4
    assert check_rule(rules["JGJT440-2018:3.0.3"], 0.8)["passed"]
    assert not check_rule(rules["JGJT440-2018:3.0.3"], 0.79)["passed"]
    assert check_rule(rules["JGJT440-2018:5.2.1:pressure"], 0.15)["passed"]
    assert not check_rule(rules["GBT18883-2022:4.2:co2"], 0.00101)["passed"]
    assert check_rule(rules["GB50736-2012:3.0.6:2"], 0.1, calculated_limit=0.1)["passed"]
