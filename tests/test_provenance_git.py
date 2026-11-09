"""算例所在仓库优先于软件安装位置。"""

import subprocess

from openresivent.core.provenance import provenance


def test_case_repository_and_dirty(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test" + chr(64) + "example.invalid"], check=True
    )
    case = tmp_path / "case.yaml"
    case.write_text("test", encoding="utf8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "case.yaml"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "test"], check=True)
    expected = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    data = provenance(case, {})
    assert data["git_commit"] == expected
    assert data["git_dirty"] is False
    case.write_text("changed", encoding="utf8")
    assert provenance(case, {})["git_dirty"] is True
