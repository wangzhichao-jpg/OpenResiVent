"""两项 M5 书稿算例的合成逐时气象端到端测试。"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.energy.examples import weather_files

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def synthetic_epw(tmp_path_factory):
    folder = tmp_path_factory.mktemp("synthetic-epw")
    start = datetime(2021, 1, 1)
    rows = []
    for i in range(8760):
        now = start + timedelta(hours=i)
        temperature = 0 if now.month in (1, 2, 3, 11, 12) else 35
        rows.append(
            f"{now.year},{now.month},{now.day},{now.hour + 1},60,X,{temperature},0,60,101325\n"
        )
    text = "header\n" * 8 + "".join(rows)
    for city in ("harbin", "beijing", "shanghai", "guangzhou"):
        (folder / (city + ".epw")).write_text(text, encoding="utf8")
    return folder


@pytest.mark.parametrize("ident", ["ex4-01", "ex4-03"])
def test_energy_book_cli(tmp_path, monkeypatch, synthetic_epw, ident):
    monkeypatch.setenv("ORV_WEATHER_DIR", str(synthetic_epw))
    path = ROOT / "cases/book/ch04" / f"{ident}.yaml"
    result = CliRunner().invoke(app, ["run", str(path), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.exception
    payload = json.loads((tmp_path / f"{ident}.json").read_text(encoding="utf8"))
    fragment = (tmp_path / f"{ident}.md").read_text(encoding="utf8")
    assert set(payload["cities"]) == {"harbin", "beijing", "shanghai", "guangzhou"}
    assert all(len(value) == 64 for value in payload["provenance"]["data_sha256"].values())
    assert len(payload["provenance"]["input_sha256"]) == 64
    assert all(v["load_reduction"] > 0 for v in payload["cities"].values())
    assert "敏感性说明" in fragment and "假设" in fragment
    assert "质量残差" not in fragment
    import re

    assert not re.search(r"合成禁词|(?:GBT|JGJT|GB)\d{3,}-\d{4}:", fragment)
    assert len(payload["cities"]["beijing"]["sensitivity"]) == 2


def test_missing_weather(monkeypatch):
    monkeypatch.delenv("ORV_WEATHER_DIR", raising=False)
    with pytest.raises(RuntimeError, match="ORV_WEATHER_DIR"):
        weather_files()
