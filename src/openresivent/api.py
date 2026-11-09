"""仅本机使用的 API；用户输入只在受控临时目录中短暂存在。"""

import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from openresivent.cli import run
from openresivent.core.case import Case
from openresivent.core.runner import PACKS, load_rules
from openresivent.report.docx_report import generate
from openresivent.report.special_reports import generate_special

app = FastAPI(title="住宅通风计算服务")


@app.middleware("http")
async def content_security(request: Request, call_next):
    """仅允许同源资源；组件库运行时样式需要内联样式。"""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# 明确列出不从请求读取外部路径的算例；不允许注入任意路径或任意模块。
ALLOWED = (
    "co2",
    "ventrate",
    "dwelling_pressure",
    "ductless",
    "shaft",
    "product_test",
    "report_shaft",
    "report_commissioning",
)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """将请求校验错误转成中文，避免回显敏感输入。"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "请求字段缺失或类型不正确",
            "errors": [
                {
                    "path": ".".join(str(x) for x in e["loc"] if x != "body"),
                    "message": "必填字段缺失" if e["type"] == "missing" else "字段类型或格式不正确",
                }
                for e in exc.errors()
            ],
        },
    )


def _validate_input(case: Case) -> None:
    """对公开工作流做字段级类型及必填检查，不回显输入值。"""
    fields = {
        "co2": {
            "occupants": float,
            "co2_l_h_person": float,
            "co2_outdoor_ppm": float,
            "co2_limit_ppm": float,
        },
        "ventrate": {
            "area_m2": float,
            "floor_area_m2": float,
            "height_m": float,
            "occupants": float,
            "outdoor_ppm": float,
            "limit_ppm": float,
            "allowance": float,
            "bedrooms": list,
            "living": dict,
        },
        "dwelling_pressure": {
            "bedrooms": int,
            "volume_m3": float,
            "n50_per_h": list,
            "kitchen_open": bool,
            "door_gap_area_m2": float,
            "transfer_area_m2": float,
            "density_kg_m3": float,
            "hood_m3_h": float,
            "fresh_supply_m3_h": float,
            "fresh_exhaust_m3_h": float,
            "opening_area_m2": float,
            "mechanical_makeup_m3_h": float,
            "hood_room": str,
            "supply_room": str,
            "exhaust_room": str,
            "bath_fan_room": str,
            "threshold_pa": float,
        },
        "ductless": {
            "area_m2": float,
            "height_m": float,
            "occupants": float,
            "whole_area_per_person_m2": float,
            "co2_l_h_person": float,
            "outdoor_ppm": float,
            "limit_ppm": float,
            "rated_m3_h": float,
            "devices": int,
            "effectiveness": list,
            "speed_m_s": float,
            "layout": str,
            "spacing_m": float,
            "opposed": bool,
        },
        "product_test": {
            "supply_mass_kg_s": float,
            "exhaust_mass_kg_s": float,
            "outdoor_t_k": float,
            "exhaust_t_k": float,
            "supply_t_k": float,
            "outdoor_w": float,
            "exhaust_w": float,
            "supply_w": float,
            "fan_flow_m3_h": float,
            "fan_pressure_pa": float,
            "fan_power_w": float,
            "speed_ratio": float,
            "test_flow_m3_h": float,
            "test_power_w": float,
            "pm25_efficiency": float,
            "kind": str,
        },
        "report_shaft": {"shaft": dict, "dwelling": dict},
        "report_commissioning": {"acceptance": dict, "maintenance": dict},
    }
    errors = []
    for key, typ in fields.get(case.module, {}).items():
        if key not in case.input:
            errors.append({"path": f"input.{key}", "message": "必填字段缺失"})
        elif typ is float and (
            isinstance(case.input[key], bool) or not isinstance(case.input[key], (int, float))
        ):
            errors.append({"path": f"input.{key}", "message": "应为数字"})
        elif typ is not float and (
            not isinstance(case.input[key], typ) or typ is int and isinstance(case.input[key], bool)
        ):
            errors.append(
                {
                    "path": f"input.{key}",
                    "message": {
                        "int": "应为整数",
                        "str": "应为文本",
                        "bool": "应为布尔值",
                        "dict": "应为对象",
                        "list": "应为列表",
                    }.get(typ.__name__, "类型不正确"),
                }
            )

    def check(obj, schema, path):
        if not isinstance(obj, dict):
            errors.append({"path": path, "message": "应为对象"})
            return
        for key, typ in schema.items():
            loc = f"{path}.{key}"
            if key not in obj:
                errors.append({"path": loc, "message": "必填字段缺失"})
                continue
            val = obj[key]
            if typ is float and (isinstance(val, bool) or not isinstance(val, (float, int))):
                errors.append({"path": loc, "message": "应为数字"})
            elif typ is not float and (
                not isinstance(val, typ) or typ is int and isinstance(val, bool)
            ):
                errors.append(
                    {
                        "path": loc,
                        "message": {
                            int: "应为整数",
                            str: "应为文本",
                            bool: "应为布尔值",
                            dict: "应为对象",
                            list: "应为列表",
                        }.get(typ, "类型不正确"),
                    }
                )

    room = {"area_m2": float, "height_m": float, "occupants": float}

    def material_fields(obj, path):
        if "hcho_materials" not in obj:
            return
        materials = obj["hcho_materials"]
        if not isinstance(materials, list):
            errors.append({"path": path + ".hcho_materials", "message": "应为列表"})
            return
        for i, material in enumerate(materials):
            check(material, {"ef_mg_m2_h": float, "area_m2": float}, f"{path}.hcho_materials.{i}")

    def rooms(d, path):
        material_fields(d, path)
        if isinstance(d.get("bedrooms"), list):
            if not d["bedrooms"]:
                errors.append({"path": path + ".bedrooms", "message": "至少需要一个卧室"})
            for i, r in enumerate(d["bedrooms"]):
                check(r, room, f"{path}.bedrooms.{i}")
                if isinstance(r, dict) and "activity" in r and not isinstance(r["activity"], str):
                    errors.append({"path": f"{path}.bedrooms.{i}.activity", "message": "应为文本"})
                if isinstance(r, dict) and "hcho_materials" in r:
                    if not isinstance(r["hcho_materials"], list):
                        errors.append(
                            {"path": f"{path}.bedrooms.{i}.hcho_materials", "message": "应为列表"}
                        )
                    else:
                        for j, m in enumerate(r["hcho_materials"]):
                            check(
                                m,
                                {"ef_mg_m2_h": float, "area_m2": float},
                                f"{path}.bedrooms.{i}.hcho_materials.{j}",
                            )
        if isinstance(d.get("living"), dict):
            check(d["living"], {"area_m2": float, "height_m": float}, path + ".living")
            material_fields(d["living"], path + ".living")

    def home(d, path):
        check(d, fields["dwelling_pressure"], path)
        if isinstance(d.get("n50_per_h"), list):
            for i, value in enumerate(d["n50_per_h"]):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append({"path": f"{path}.n50_per_h.{i}", "message": "应为数字"})

    d = case.input

    def positive(obj, keys, path):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, (float, int)) and not isinstance(value, bool) and value <= 0:
                errors.append({"path": f"{path}.{key}", "message": "必须大于零"})

    positive(
        d,
        (
            "area_m2",
            "height_m",
            "occupants",
            "volume_m3",
            "density_kg_m3",
            "rated_m3_h",
            "test_power_w",
            "test_flow_m3_h",
        ),
        "input",
    )
    if case.module == "ventrate" and isinstance(d.get("bedrooms"), list):
        for i, r in enumerate(d["bedrooms"]):
            if isinstance(r, dict):
                positive(r, ("area_m2", "height_m"), f"input.bedrooms.{i}")
    if case.module == "ventrate":
        rooms(d, "input")
        if "noise" in d:
            check(
                d["noise"],
                {
                    "reference_flow_m3_s": float,
                    "flows_m3_s": list,
                    "stages": list,
                    "terminal_reflection_db": list,
                    "directivity": float,
                    "distance_m": float,
                    "room_constant_m2": float,
                    "target_db": float,
                },
                "input.noise",
            )
            if isinstance(d["noise"], dict) and "fan_power_db" not in d["noise"]:
                check(
                    d["noise"],
                    {
                        "fan_pressure_pa": float,
                        "fan_specific_level_db": float,
                        "fan_octave_offsets_db": list,
                    },
                    "input.noise",
                )
    if case.module == "dwelling_pressure":
        home(d, "input")
    if case.module == "ductless" and isinstance(d.get("effectiveness"), list):
        for i, x in enumerate(d["effectiveness"]):
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                errors.append({"path": f"input.effectiveness.{i}", "message": "应为数字"})
            elif not 0 <= x <= 1:
                errors.append({"path": f"input.effectiveness.{i}", "message": "应在0至1之间"})
    if (
        case.module == "product_test"
        and isinstance(d.get("pm25_efficiency"), (int, float))
        and not isinstance(d.get("pm25_efficiency"), bool)
        and not 0 <= d["pm25_efficiency"] <= 1
    ):
        errors.append({"path": "input.pm25_efficiency", "message": "应在0至1之间"})

    def shaft_fields(obj, path):
        from dataclasses import fields as dataclass_fields

        from openresivent.shaft.model import ShaftConfig

        definitions = {x.name: x.type for x in dataclass_fields(ShaftConfig)}
        for key, value in obj.items():
            if key not in definitions:
                errors.append({"path": f"{path}.{key}", "message": "未知字段"})
                continue
            typ = definitions[key]
            if typ is float and (isinstance(value, bool) or not isinstance(value, (int, float))):
                errors.append({"path": f"{path}.{key}", "message": "应为数字"})
            elif typ in (int, str) and (
                not isinstance(value, typ) or typ is int and isinstance(value, bool)
            ):
                errors.append({"path": f"{path}.{key}", "message": "字段类型不正确"})
        positive(
            obj,
            (
                "floors",
                "floor_height",
                "width",
                "depth",
                "inside_temperature",
                "outside_temperature",
                "roof_area",
            ),
            path,
        )
        fraction = obj.get("fraction")
        if (
            isinstance(fraction, (int, float))
            and not isinstance(fraction, bool)
            and not 0 < fraction <= 1
        ):
            errors.append({"path": f"{path}.fraction", "message": "应大于0且不超过1"})

    if case.module == "shaft":
        shaft_fields(d, "input")
    if case.module == "report_shaft":
        if isinstance(d.get("dwelling"), dict):
            home(d["dwelling"], "input.dwelling")
        if isinstance(d.get("shaft"), dict):
            shaft_fields(d["shaft"], "input.shaft")
    if case.module == "report_commissioning":
        if isinstance(d.get("maintenance"), dict):
            check(
                d["maintenance"],
                {
                    "core": str,
                    "initial_latent": float,
                    "after_clean_latent": float,
                    "filter_pressure_ratio": float,
                },
                "input.maintenance",
            )
        if isinstance(d.get("acceptance"), dict):
            acceptance = d["acceptance"]
            if "records" not in acceptance:
                check(
                    acceptance,
                    {
                        "start": str,
                        "seed": int,
                        "worst_day_indexes": list,
                        "outdoor_high_ug_m3": float,
                        "outdoor_base_ug_m3": float,
                        "indoor_base_ug_m3": float,
                        "noise_std_ug_m3": float,
                        "co2_ppm": float,
                        "spot_duration_minutes": int,
                    },
                    "input.acceptance",
                )
            elif "spot_records" not in acceptance:
                errors.append({"path": "input.acceptance.spot_records", "message": "必填字段缺失"})
            for field in ("records", "spot_records", "retest_records"):
                if field not in acceptance:
                    continue
                records = acceptance[field]
                if not isinstance(records, list):
                    errors.append({"path": f"input.acceptance.{field}", "message": "应为列表"})
                    continue
                required = {"time": str, "indoor_pm": float, "indoor_co2": float}
                if field == "records":
                    required["outdoor_pm"] = float
                for i, row in enumerate(records):
                    check(row, required, f"input.acceptance.{field}.{i}")
            for key in (
                "total_design_m3_h",
                "total_measured_m3_h",
                "terminal_design_m3_h",
                "terminal_measured_m3_h",
                "total_homes",
            ):
                check(d["acceptance"], {key: float}, "input.acceptance")
    if errors:
        raise HTTPException(status_code=422, detail=errors)


def _prepare(case: Case, root: Path) -> Path:
    if case.module not in ALLOWED:
        raise ValueError("该模块未开放 API 或需要外部数据")
    _validate_input(case)
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(case.model_dump(), allow_unicode=True), encoding="utf8")
    return path


@app.get("/modules")
def modules():
    return {"modules": list(ALLOWED), "reports": ["design", "shaft", "commissioning"]}


@app.get("/rules")
def rules():
    rows = []
    from openresivent.report.docx_report import standard_name

    for pack in PACKS:
        rules, _versions = load_rules([pack])
        for r in rules.values():
            rows.append(
                {
                    "standard": standard_name(pack),
                    "clause": r.get("source", "").split("，")[0],
                    "strength": r.get("strength", ""),
                    "requirement": r.get("title", ""),
                }
            )
    return {"rules": rows}


@app.post("/run")
async def run_case(case: Case, request: Request, response: Response):
    try:
        with TemporaryDirectory(prefix="orv-api-") as tmp:
            path = _prepare(case, Path(tmp))
            run(path, Path(tmp) / "out")
            result = json.loads((Path(tmp) / "out" / f"{case.meta.id}.json").read_text())
            canonical = json.dumps(
                case.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
            result["provenance"]["request_sha256"] = hashlib.sha256(canonical).hexdigest()
            from openresivent.core.provenance import provenance

            repo = Path(__file__).resolve().parents[2]
            repo_info = (
                provenance(repo / "pyproject.toml", {})
                if (repo / "pyproject.toml").is_file()
                else {}
            )
            result["provenance"]["git_commit"] = repo_info.get("git_commit", "unknown")
            result["provenance"]["git_dirty"] = repo_info.get("git_dirty")
            from openresivent.core.module_names import ALIASES

            old = (await request.json()).get("module")
            if old in ALIASES:
                response.headers["Deprecation"] = "true"
                response.headers["Warning"] = '299 - "Deprecated module alias"'
            return result
    except KeyError as exc:
        raise HTTPException(
            status_code=422, detail=[{"path": f"input.{exc.args[0]}", "message": "必填字段缺失"}]
        ) from exc
    except (ValueError, TypeError, FileNotFoundError, ArithmeticError) as exc:
        raise HTTPException(
            status_code=422, detail=[{"path": "input", "message": "参数类型、范围或组合无效"}]
        ) from exc


@app.post("/report")
async def report_case(case: Case, request: Request, type: str = "design"):
    try:
        with TemporaryDirectory(prefix="orv-api-") as tmp:
            path = _prepare(case, Path(tmp))
            out = Path(tmp) / "report.docx"
            if type == "design":
                generate(path, out)
            elif type in ("shaft", "commissioning"):
                generate_special(path, out, type)
            else:
                raise ValueError("报告类型无效")
            data = out.read_bytes()
        from openresivent.core.module_names import ALIASES

        old = (await request.json()).get("module")
        headers = (
            {"Deprecation": "true", "Warning": '299 - "Deprecated module alias"'}
            if old in ALIASES
            else {}
        )
        return Response(
            data,
            headers=headers,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=422, detail=[{"path": f"input.{exc.args[0]}", "message": "必填字段缺失"}]
        ) from exc
    except (ValueError, TypeError, FileNotFoundError, ArithmeticError) as exc:
        raise HTTPException(
            status_code=422, detail=[{"path": "input", "message": "参数类型、范围或报告类型无效"}]
        ) from exc


_sweep_jobs = {}


@app.post("/sweep", status_code=202)
def submit_sweep(request: Request, payload: dict):
    """异步执行本机扫描，仅接受无外部文件的公开模块。"""
    import threading
    import uuid

    from openresivent.sweep import run_sweep, samples

    if request.client and request.client.host not in ("127.0.0.1", "::1", "testclient"):
        raise HTTPException(status_code=403, detail="仅限本机访问")
    try:
        base = Case.model_validate(payload["case"]).model_dump()
        if base["module"] not in ("shaft", "dwelling_pressure", "co2", "makeup_design"):
            raise ValueError("扫描模块未开放")
        spec = payload["spec"]
        plan = samples(spec)
        import re

        name = payload.get("out", uuid.uuid4().hex)
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name):
            raise ValueError("输出目录只允许安全的单级子目录名")
        root = (
            Path(
                os.environ.get(
                    "ORV_SWEEP_DIR", str(Path.home() / ".local/share/openresivent/sweeps")
                )
            )
            .expanduser()
            .resolve()
        )
        root.mkdir(parents=True, exist_ok=True)
        out = root / name
        if out.is_symlink() or not out.resolve().is_relative_to(root):
            raise ValueError("输出目录不得为符号链接或越出扫描根目录")
        out.mkdir(exist_ok=True)
        if out.is_symlink() or not out.resolve().is_relative_to(root):
            raise ValueError("输出目录不得为符号链接或越出扫描根目录")
        if any(p.is_symlink() for p in out.rglob("*")):
            raise ValueError("输出目录中不允许符号链接")
        workers = int(payload.get("workers", 1))
        if workers < 1 or workers > 8 or len(plan) > 100000:
            raise ValueError("进程数或样本数超出范围")
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job = uuid.uuid4().hex
    _sweep_jobs[job] = {"status": "running", "completed": 0, "total": len(plan), "output": str(out)}

    def task():
        try:
            result = run_sweep(spec, base, out, workers)
            _sweep_jobs[job].update(result, status="completed")
        except Exception as exc:  # noqa: BLE001
            _sweep_jobs[job].update(status="failed", error=str(exc))

    threading.Thread(target=task, daemon=True).start()
    return {"job_id": job, **_sweep_jobs[job]}


@app.get("/sweep/{job_id}")
def sweep_progress(job_id: str, request: Request):
    """查询本进程提交的任务进度。"""
    import sqlite3

    if request.client and request.client.host not in ("127.0.0.1", "::1", "testclient"):
        raise HTTPException(status_code=403, detail="仅限本机访问")
    if job_id not in _sweep_jobs:
        raise HTTPException(status_code=404, detail="任务不存在")
    state = dict(_sweep_jobs[job_id])
    db = Path(state["output"]) / "samples.sqlite3"
    if db.exists():
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
                state["completed"] = conn.execute("select count(*) from samples").fetchone()[0]
        except sqlite3.Error:
            pass
    return state


@app.get("/sweep/{job_id}/results")
def sweep_results(job_id: str, request: Request):
    """读取已完成任务的汇总统计。"""
    state = sweep_progress(job_id, request)
    if state["status"] != "completed":
        raise HTTPException(status_code=409, detail="扫描尚未完成")
    root = (
        Path(os.environ.get("ORV_SWEEP_DIR", str(Path.home() / ".local/share/openresivent/sweeps")))
        .expanduser()
        .resolve()
    )
    directory = Path(state["output"])
    if directory.is_symlink() or directory.resolve().parent != root:
        raise HTTPException(status_code=403, detail="扫描目录无效")
    path = directory / "statistics.json"
    if path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=404, detail="统计文件不存在")
    return json.loads(path.read_text(encoding="utf8"))


@app.get("/sweep/{job_id}/files/{filename}")
def sweep_download(job_id: str, filename: str, request: Request):
    """只允许下载白名单内的已完成扫描产物。"""
    if filename not in ("samples.csv", "results.xlsx", "summary.docx"):
        raise HTTPException(status_code=404, detail="文件不存在")
    state = sweep_progress(job_id, request)
    if state["status"] != "completed":
        raise HTTPException(status_code=409, detail="扫描尚未完成")
    root = (
        Path(os.environ.get("ORV_SWEEP_DIR", str(Path.home() / ".local/share/openresivent/sweeps")))
        .expanduser()
        .resolve()
    )
    directory = Path(state["output"])
    if directory.is_symlink() or directory.resolve().parent != root:
        raise HTTPException(status_code=403, detail="扫描目录无效")
    path = directory / filename
    if path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=filename)


@app.get("/{asset_path:path}", include_in_schema=False)
def ui(asset_path: str):
    """仅提供本地生成的前端，不代理远程文件。"""
    roots = []
    if os.environ.get("ORV_WEB_DIR"):
        roots.append(Path(os.environ["ORV_WEB_DIR"]))
    roots.extend(
        [Path(__file__).resolve().parent / "web", Path(__file__).resolve().parents[2] / "build/web"]
    )
    root = next((p.resolve() for p in roots if (p / "index.html").is_file()), None)
    if root is None:
        if not asset_path:
            return HTMLResponse(
                '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>界面尚未构建</title><h1>界面尚未构建</h1><p>请在源码目录运行 npm ci 和 npm run build，然后重新安装软件；也可通过 ORV_WEB_DIR 指定已构建目录。</p></html>'
            )
        raise HTTPException(status_code=404, detail="页面文件不存在")
    target = (root / (asset_path or "index.html")).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="页面文件不存在")
    return FileResponse(target)
