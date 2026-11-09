"""算例溯源：文件哈希、所在仓库提交和工作区状态。"""

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from openresivent import __version__


def provenance(
    path: Path, rule_packs: dict[str, str], data_files: dict[str, Path] | None = None
) -> dict:
    """输入文件路径、规则包版本及数据文件路径 → 溯源字典，不涉及物理单位。"""
    revision, dirty = "unknown", None
    for directory in (
        path.resolve().parent,
        Path(os.environ["ORV_REPO"]) if os.environ.get("ORV_REPO") else None,
        Path(__file__).resolve().parents[3],
    ):
        if directory is None:
            continue
        try:

            def git(*args, cwd=directory):
                return subprocess.check_output(
                    ["git", *args], cwd=cwd, stderr=subprocess.DEVNULL, text=True, timeout=5
                ).strip()

            revision = git("rev-parse", "HEAD")
            dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
            break
        except (OSError, subprocess.SubprocessError):
            continue
    data_hashes = {
        name: hashlib.sha256(p.read_bytes()).hexdigest() for name, p in (data_files or {}).items()
    }
    return {
        "software_version": __version__,
        "git_commit": revision,
        "git_dirty": dirty,
        "rule_packs": rule_packs,
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "data_sha256": data_hashes,
        "run_time": datetime.now(UTC).isoformat(),
    }


def parameter_data_path(name: str):
    """返回参数表实际路径，name 为无路径分隔符的文件名。"""
    if Path(name).name != name:
        raise ValueError("参数表名称无效")
    path = Path(__file__).resolve().parents[3] / "data" / name
    return path if path.is_file() else files("openresivent").joinpath("data", name)


def activity_data_path():
    """返回实际使用的活动分档数据文件，返回路径，不涉及物理单位。"""
    return parameter_data_path("co2_activity.yaml")
