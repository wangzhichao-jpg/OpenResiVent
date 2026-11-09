"""独立由 CSV 复算全因子分组与主效应。"""

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def verify(folder, thresholds):
    """核对统计量和离散水平，返回已检查项数。"""
    with (folder / "samples.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    stats = json.loads((folder / "statistics.json").read_text())
    count = 0
    for metric, summary in stats["metrics"].items():
        values = np.array([float(row[metric]) for row in rows])
        p = np.percentile(values, [0, 10, 50, 90, 100])
        for x, y in zip(summary.values(), p, strict=True):
            if abs(x - y) > 1e-9:
                raise AssertionError((metric, x, y))
            count += 1
    for g in stats["groups"]:

        def matches(value, level):
            try:
                return float(value) == float(level)
            except (ValueError, TypeError):
                return value == str(level)

        matched = [r for r in rows if matches(r[g["factor"]], g["level"])]
        values = [float(r[g["metric"]]) for r in matched]
        if len(values) != g["count"] or abs(sum(values) / len(values) - g["mean"]) > 1e-9:
            raise AssertionError(g)
        if g["pass_rate"] is not None:
            rate = sum(v >= thresholds[g["metric"]] for v in values) / len(values)
            if abs(rate - g["pass_rate"]) > 1e-9:
                raise AssertionError(g)
        count += 1
    for s in stats["sensitivity"]:
        groups = [
            g["mean"]
            for g in stats["groups"]
            if g["metric"] == s["metric"] and g["factor"] == s["factor"]
        ]
        if abs(s["value"] - (max(groups) - min(groups))) > 1e-9:
            raise AssertionError(s)
        count += 1
    return count


def main():
    for name, t in [("shaft-study", {"bottom_m3_s": 300 / 3600}), ("makeup-study", {})]:
        print(name, "已复核", verify(ROOT / "build/parameter-sweep" / name, t), "项")


if __name__ == "__main__":
    main()
