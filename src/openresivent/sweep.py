"""可复现的本地批量扫描；结果仅写入指定目录。"""

import copy
import csv
import hashlib
import itertools
import json
import math
import multiprocessing
import sqlite3
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import qmc, rankdata

from openresivent.core.case import Case


def get_path(obj, path):
    """按点分路径读取嵌套字段，列表使用从零开始的索引。"""
    for part in path.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def set_path(obj, path, value):
    """只修改已有字段，防止无效因子静默加入输入。"""
    parts = path.split(".")
    parent = get_path(obj, ".".join(parts[:-1])) if len(parts) > 1 else obj
    key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
    if isinstance(parent, dict) and key not in parent:
        raise ValueError(f"未知输入字段：{path}")
    parent[key] = value


def samples(spec):
    """确定性生成全因子或给定种子的拉丁超立方样本。"""
    factors = spec["factors"]
    names = list(factors)
    if not names:
        raise ValueError("扫描因子不能为空")
    if spec["method"] == "factorial":
        levels = [factors[n]["values"] for n in names]
        if any(not isinstance(x, list) or not x for x in levels):
            raise ValueError("全因子水平不能为空")
        return [dict(zip(names, x, strict=True)) for x in itertools.product(*levels)]
    if spec["method"] != "lhs" or "seed" not in spec:
        raise ValueError("抽样方式错误或缺少随机种子")
    n = int(spec["count"])
    if n < 2:
        raise ValueError("样本数至少为2")
    unit = qmc.LatinHypercube(d=len(names), seed=int(spec["seed"])).random(n)
    result = []
    for row in unit:
        vals = []
        for name, u in zip(names, row, strict=True):
            factor = factors[name]
            if "values" in factor:
                v = factor["values"]
                vals.append(v[min(int(u * len(v)), len(v) - 1)])
            else:
                lo, hi = map(float, factor["range"])
                if not lo < hi:
                    raise ValueError("连续范围无效")
                vals.append(float(lo + u * (hi - lo)))
        result.append(dict(zip(names, vals, strict=True)))
    return result


def _execute(payload):
    idx, base, factors, metrics, workdir = payload
    from openresivent.cli import run

    c = copy.deepcopy(base)
    for k, v in factors.items():
        set_path(c["input"], k, v)
    Case.model_validate(c)
    with tempfile.TemporaryDirectory(prefix=".orv-sweep-", dir=workdir) as tmp:
        p = Path(tmp) / "case.yaml"
        p.write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf8")
        run(p, Path(tmp) / "out")
        output = json.loads((Path(tmp) / "out" / f"{c['meta']['id']}.json").read_text())
    values = {k: get_path(output, path) for k, path in metrics.items()}
    if any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
        for x in values.values()
    ):
        raise ValueError("输出指标必须是有限数值")
    return idx, {
        "sample": idx,
        "factors": factors,
        "input": c["input"],
        "case": c,
        "metrics": values,
        "provenance": output["provenance"],
    }


def statistics(rows, spec):
    """返回分位数、分类达标率和敏感性；全因子主效应或秩回归。"""
    result = {"metrics": {}, "groups": [], "sensitivity": []}
    factors = list(spec["factors"])
    method = spec["method"]
    for name in spec["metrics"]:
        y = np.array([r["metrics"][name] for r in rows], dtype=float)
        result["metrics"][name] = dict(
            zip(
                ["min", "p10", "p50", "p90", "max"],
                map(float, np.percentile(y, [0, 10, 50, 90, 100])),
                strict=True,
            )
        )
        criterion = spec.get("criteria", {}).get(name)
        passed = None
        if criterion:
            if "rule" in criterion:
                from openresivent.core.runner import load_rules

                rules, _ = load_rules([criterion["pack"]])
                rule = rules[criterion["rule"]]
                op = rule["check"]["op"]
                limit = rule["check"]["limit"]
            else:
                op = criterion["op"]
                limit = criterion["limit"]
            if op not in ("min", "max") or not isinstance(limit, (float, int)):
                raise ValueError("仅支持数值上下限判据")
            passed = y >= limit if op == "min" else y <= limit
        for factor in factors:
            values = [r["factors"][factor] for r in rows]
            if method == "factorial" or "values" in spec["factors"][factor]:
                levels = list(dict.fromkeys(values))
                means = []
                for level in levels:
                    mask = np.array([v == level for v in values])
                    mean = float(y[mask].mean())
                    means.append(mean)
                    result["groups"].append(
                        {
                            "metric": name,
                            "factor": factor,
                            "level": level,
                            "count": int(mask.sum()),
                            "mean": mean,
                            "pass_rate": float(passed[mask].mean()) if passed is not None else None,
                        }
                    )
                if method == "factorial":
                    result["sensitivity"].append(
                        {
                            "metric": name,
                            "factor": factor,
                            "method": "主效应极差",
                            "value": max(means) - min(means),
                        }
                    )
        if method == "lhs":

            def encode(factor, value):
                try:
                    return float(value)
                except (ValueError, TypeError):
                    levels = spec["factors"][factor].get("values")
                    if not levels or value not in levels:
                        raise ValueError("分类因子须明确给定水平顺序") from None
                    return float(levels.index(value))

            x = np.array([[encode(f, r["factors"][f]) for f in factors] for r in rows])
            ranked = np.column_stack([rankdata(x[:, i]) for i in range(x.shape[1])])
            yr = rankdata(y)
            scale = ranked.std(axis=0)
            ys = yr.std()
            if (scale == 0).any() or ys == 0:
                raise ValueError("常量因子或指标无法计算秩回归")
            design = (ranked - ranked.mean(axis=0)) / scale
            beta = np.linalg.lstsq(design, (yr - yr.mean()) / ys, rcond=None)[0]
            for f, v in zip(factors, beta, strict=True):
                result["sensitivity"].append(
                    {"metric": name, "factor": f, "method": "SRRC", "value": float(v)}
                )
    return result


def run_sweep(spec, base, out, workers=1):
    """执行扫描并持久续算；base 为完整案例对象，out 为唯一输出目录。"""
    from openresivent import __version__
    from openresivent.core.runner import PACKS, load_rules

    model = Case.model_validate(base)
    if model.module not in ("shaft", "dwelling_pressure", "co2", "makeup_design"):
        raise ValueError("该扫描模块未开放或依赖外部资料")
    packs = {}
    for criterion in spec.get("criteria", {}).values():
        if "rule" in criterion:
            _, versions = load_rules([criterion["pack"]])
            packs.update(versions)
    for c in spec.get("criteria", {}).values():
        if "rule" in c and c.get("pack") not in PACKS:
            raise ValueError("仅允许公开规则包")
    if workers < 1:
        raise ValueError("进程数必须为正")
    plan = samples(spec)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    import sys
    from importlib.resources import files

    from openresivent.core.provenance import parameter_data_path

    package = Path(__file__).resolve().parent
    code = hashlib.sha256()
    if getattr(sys, "frozen", False):
        code.update(Path(sys.executable).read_bytes())
    else:
        for path in sorted(package.rglob("*.py")):
            code.update(str(path.relative_to(package)).encode())
            code.update(path.read_bytes())
    for name in sorted(PACKS.values()):
        code.update(name.encode())
        code.update(files("openresivent").joinpath("rules", "packs", name).read_bytes())
    for name in (
        "co2_activity.yaml",
        "pah_tef.yaml",
        "hcho_emission.yaml",
        "exposure_defaults.yaml",
        "param_meta.yaml",
        "duct_fittings.yaml",
    ):
        code.update(name.encode())
        code.update(parameter_data_path(name).read_bytes())
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "spec": spec,
                "base": base,
                "software_version": __version__,
                "rules": packs,
                "code_sha256": code.hexdigest(),
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    lock = out / ".sweep.lock"
    import fcntl

    with lock.open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = sqlite3.connect(out / "samples.sqlite3")
        try:
            db.execute("create table if not exists meta (fingerprint text)")
            prev = db.execute("select fingerprint from meta").fetchone()
            if prev and prev[0] != fingerprint:
                raise ValueError("扫描定义已变更，不能复用输出目录")
            if not prev:
                db.execute("insert into meta values (?)", (fingerprint,))
                db.commit()
            db.execute(
                "create table if not exists samples (id integer primary key, payload text not null)"
            )
            db.commit()
            done = {x[0] for x in db.execute("select id from samples")}
            pending = [
                (i, base, f, spec["metrics"], str(out.resolve()))
                for i, f in enumerate(plan)
                if i not in done
            ]
            with ProcessPoolExecutor(
                max_workers=workers, mp_context=multiprocessing.get_context("spawn")
            ) as pool:
                for idx, row in pool.map(_execute, pending):
                    row["provenance"]["criterion_rule_versions"] = packs
                    db.execute(
                        "insert into samples values (?,?)",
                        (idx, json.dumps(row, ensure_ascii=False, sort_keys=True)),
                    )
                    db.commit()
            rows = [json.loads(r[0]) for r in db.execute("select payload from samples order by id")]
            stats = statistics(rows, spec)
            export(out, rows, stats)
            return {
                "completed": len(rows),
                "total": len(plan),
                "output": str(out),
                "fingerprint": fingerprint,
            }
        finally:
            db.close()


def export(out, rows, stats):
    """输出逐样本 CSV、XLSX、统计 JSON 和 DOCX。"""
    from docx import Document
    from openpyxl import Workbook

    names = ["sample"] + list(rows[0]["factors"]) + list(rows[0]["metrics"])
    data = [[r["sample"], *r["factors"].values(), *r["metrics"].values()] for r in rows]
    with (out / "samples.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(names)
        w.writerows(data)
    wb = Workbook()
    ws = wb.active
    ws.title = "样本"
    ws.append(names)
    for row in data:
        ws.append(row)
    ws = wb.create_sheet("统计")
    ws.append(["指标", "最小", "P10", "P50", "P90", "最大"])
    for k, v in stats["metrics"].items():
        ws.append([k, *v.values()])
    ws = wb.create_sheet("分组")
    headers = ["metric", "factor", "level", "count", "mean", "pass_rate"]
    ws.append(headers)
    for row in stats["groups"]:
        ws.append([row[k] for k in headers])
    ws = wb.create_sheet("敏感性")
    headers = ["metric", "factor", "method", "value"]
    ws.append(headers)
    for row in stats["sensitivity"]:
        ws.append([row[k] for k in headers])
    wb.save(out / "results.xlsx")
    (out / "statistics.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    doc = Document()
    doc.add_heading("批量计算汇总", 0)
    doc.add_paragraph(f"样本数：{len(rows)}。结果只反映指定假设，不替代现场验证。")
    table = doc.add_table(rows=1, cols=6)
    for c, text in zip(
        table.rows[0].cells, ["指标", "最小", "P10", "P50", "P90", "最大"], strict=True
    ):
        c.text = text
    for k, v in stats["metrics"].items():
        cells = table.add_row().cells
        for c, value in zip(cells, [k, *v.values()], strict=True):
            c.text = str(value)
    for title, records, keys in [
        ("分组结果", stats["groups"], ["metric", "factor", "level", "count", "mean", "pass_rate"]),
        ("敏感性", stats["sensitivity"], ["metric", "factor", "method", "value"]),
    ]:
        doc.add_heading(title, level=1)
        table = doc.add_table(rows=1, cols=len(keys))
        for cell, key in zip(table.rows[0].cells, keys, strict=True):
            cell.text = key
        for row in records:
            for cell, key in zip(table.add_row().cells, keys, strict=True):
                cell.text = str(row[key])
    doc.save(out / "summary.docx")
