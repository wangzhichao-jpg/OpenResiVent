"""CFD 自编模板、守恒、空气龄与 GCI；不启动 CFD。"""

import pytest

from openresivent.cfd.postprocess import patch_flux, summarize
from openresivent.cfd.template import (
    Room,
    create_room,
    from_network,
    gci,
    oscillatory_uncertainty,
    room_mesh,
    submit,
)
from openresivent.measure.ventilation import air_change_efficiency


def test_cfd_root_default_and_override(tmp_path, monkeypatch):
    from pathlib import Path

    from openresivent.cfd.config import case_root

    monkeypatch.delenv("ORV_CFD_DIR", raising=False)
    assert case_root() == (Path.home() / ".local/share/openresivent/cfd").resolve()
    monkeypatch.setenv("ORV_CFD_DIR", str(tmp_path))
    assert case_root() == tmp_path.resolve()


def test_submit_configured_command(tmp_path, monkeypatch):
    import subprocess

    seen = []
    monkeypatch.setenv("ORV_CFD_DIR", str(tmp_path))
    monkeypatch.setenv("ORV_FOAM_CMD", "/opt/foam wrapper")
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: seen.append((args, kwargs)))
    case = tmp_path / "case"
    case.mkdir()
    submit("example", case)
    args, opts = seen[0]
    assert args[:2] == ["systemd-run", "--user"] and opts["check"]
    assert "flock" in args and str(case / ".openresivent.lock") in args
    assert 'blockMesh() { command /opt/foam wrapper blockMesh "$@"; }' in args[-1]
    monkeypatch.delenv("ORV_FOAM_CMD")
    submit("direct", case)
    assert 'blockMesh() { command blockMesh "$@"; }' in seen[-1][0][-1]


def test_configured_cfd_missing_fails(tmp_path, monkeypatch):
    from openresivent.cfd.examples import comparison

    monkeypatch.setenv("ORV_CFD_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="missing-upper"):
        comparison({"upper": "missing-upper/summary.json", "lower": "missing-lower/summary.json"})


def test_comparison(tmp_path, monkeypatch):
    import json

    from openresivent.cfd.examples import comparison
    from openresivent.cfd.report import render

    x = {
        "air_change_efficiency": 0.4,
        "average_age_s": 750,
        "breathing_age_s": 800,
        "mass_balance_relative": 1e-8,
        "flow_converged": True,
        "gci_fine": 0.01,
    }
    (tmp_path / "u.json").write_text(json.dumps(x))
    (tmp_path / "l.json").write_text(json.dumps(x))
    monkeypatch.setenv("ORV_CFD_DIR", str(tmp_path))
    r = comparison({"upper": "u.json", "lower": "l.json"})
    assert len(r["upper"]["sha256"]) == 64 and "40.00%" in render(r)
    from pathlib import Path

    from openresivent.core.case import load_case
    from openresivent.core.runner import execute

    c = load_case(Path(__file__).resolve().parents[1] / "cases/book/ch06/ex6-07.yaml")
    (tmp_path / "second-order-upper-4-age-polish").mkdir()
    (tmp_path / "second-order-lower-4-age-polish").mkdir()
    (tmp_path / "second-order-upper-4-age-polish/summary.json").write_text(json.dumps(x))
    (tmp_path / "second-order-lower-4-age-polish/summary.json").write_text(json.dumps(x))
    output, _ = execute(c, Path("."))
    assert output["upper"]["average_age_s"] == 750
    with pytest.raises(ValueError):
        comparison({"upper": "../bad", "lower": "l.json"})


def test_template(tmp_path):
    c = Room()
    p = create_room(tmp_path / "case", c)
    assert "hex (" in (p / "system/blockMeshDict").read_text()
    assert "bounded Gauss linearUpwind grad(U)" in (p / "system/fvSchemes").read_text()
    assert "bounded Gauss limitedLinear 1" in (p / "system/fvSchemes").read_text()
    one = create_room(tmp_path / "first", c, scheme="first")
    assert "div(phi,U) bounded Gauss upwind" in (one / "system/fvSchemes").read_text()
    with pytest.raises(ValueError):
        create_room(tmp_path / "wrong", c, scheme="wrong")
    for f in ["0/U", "0/T", "constant/fvOptions", "system/fvSchemes"]:
        assert "自行编写" in (p / f).read_text()
    from openresivent.cfd.template import create_channel, submit_channel

    channel = create_channel(tmp_path / "channel")
    assert "(60 4 4)" in (channel / "system/blockMeshDict").read_text()
    with pytest.raises(ValueError):
        submit_channel("bad name", channel)
    with pytest.raises(FileExistsError):
        create_room(p, c)
    with pytest.raises(ValueError):
        room_mesh(Room(outlet="wrong"))
    custom = Room(
        inlet_y=1.0,
        outlet_y=2.0,
        inlet_z=1.0,
        outlet_z=1.5,
        inlet_height=0.25,
        outlet_height=0.75,
        outlet_opening=1,
    )
    assert "inlet {type patch" in room_mesh(custom)
    with pytest.raises(ValueError):
        room_mesh(Room(inlet_y=0))
    with pytest.raises(ValueError):
        create_room(tmp_path / "bad", c, diffusivity=0)
    heat = create_room(tmp_path / "heated", c, heat_w=100)
    assert "thermalSource" in (heat / "constant/fvOptions.thermal").read_text()
    with pytest.raises(ValueError):
        create_room(tmp_path / "negative", c, heat_w=-1)
    with pytest.raises(ValueError):
        submit("bad name", p)
    with pytest.raises(ValueError):
        submit("case", p)


def test_summary():
    s = summarize([10, 20], [1, 3], [0.5, 1.2], 0.1, 0.1)
    assert s["average_age_s"] == pytest.approx(17.5)
    assert s["air_change_efficiency"] == air_change_efficiency(40, 17.5)
    assert s["mass_balance_relative"] == 0
    with pytest.raises(ValueError):
        summarize([-1], [1], [0.5], 1, 1)
    with pytest.raises(ValueError):
        summarize([1], [1], [2], 1, 1)
    with pytest.raises(ValueError):
        patch_flux("none", "../invalid")


def test_m2_and_gci():
    f = [{"mass_flow": 0.12, "volume_flow": 0.1}, {"mass_flow": 0.12, "volume_flow": -0.1}]
    assert from_network(f, 0, 1) == pytest.approx(0.1)
    f[1]["volume_flow"] = -0.2
    with pytest.raises(ValueError):
        from_network(f, 0, 1)
    u = oscillatory_uncertainty([0.35, 0.36, 0.355])
    assert u["absolute"] == pytest.approx(0.005) and u["relative_fine"] == pytest.approx(
        0.005 / 0.355
    )
    with pytest.raises(ValueError):
        oscillatory_uncertainty([0.5, 0.6])
    r = gci([1.16, 1.04, 1.01], 2)
    assert r["order"] == pytest.approx(2)
    assert r["gci_fine"] == pytest.approx(1.25 * 0.03 / 1.01 / 3)
    with pytest.raises(ValueError):
        gci([1, 2, 1], 2)
