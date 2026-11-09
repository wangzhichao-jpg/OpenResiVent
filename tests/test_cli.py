import json
from pathlib import Path

from typer.testing import CliRunner

from openresivent.cli import app


def test_run(tmp_path):
    runner = CliRunner()
    case = Path("cases/book/ch02/ex2-01.yaml")
    result = runner.invoke(app, ["run", str(case), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    output = json.loads((tmp_path / "ex2-01.json").read_text())
    assert abs(output["flow_m3_s"] * 3600 - 90) < 1e-10
    assert len(output["provenance"]["input_sha256"]) == 64
    from openresivent import __version__

    assert runner.invoke(app, ["version"]).output.strip() == __version__
    assert runner.invoke(app, ["--version"]).output.strip() == __version__
