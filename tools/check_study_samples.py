"""将研究样本另存并经 CLI 单独执行以比较结果。"""

import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from openresivent.sweep import get_path

ROOT = Path(__file__).resolve().parents[1]


def main():
    for name in ("shaft", "makeup"):
        folder = ROOT / "build/p309" / f"{name}-study"
        spec = yaml.safe_load((ROOT / "cases/studies" / f"{name}_sweep.yaml").read_text())
        with sqlite3.connect(folder / "samples.sqlite3") as db:
            allrows = db.execute("select payload from samples order by id").fetchall()
        for i in (0, len(allrows) // 2, len(allrows) - 1):
            sample = json.loads(allrows[i][0])
            with tempfile.TemporaryDirectory(dir=ROOT / "build/p309") as tmp:
                tmp = Path(tmp)
                case = tmp / "sample.yaml"
                case.write_text(yaml.safe_dump(sample["case"], allow_unicode=True))
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "openresivent.cli",
                        "run",
                        str(case),
                        "--out",
                        str(tmp / "out"),
                    ],
                    check=True,
                )
                result = json.loads(
                    (tmp / "out" / f"{sample['case']['meta']['id']}.json").read_text()
                )
                for key, path in spec["metrics"].items():
                    if get_path(result, path) != sample["metrics"][key]:
                        raise AssertionError((name, i, key))
            print(name, "样本", i, "逐位一致")


if __name__ == "__main__":
    main()
