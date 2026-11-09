"""算例执行命令行。"""

import json
from pathlib import Path
from typing import Annotated

import typer

from openresivent import __version__
from openresivent.core.case import load_case
from openresivent.core.provenance import activity_data_path, parameter_data_path, provenance
from openresivent.core.runner import execute
from openresivent.report.markdown import render
from openresivent.ventrate.calculation import co2_flow

app = typer.Typer(help="住宅通风计算工具", no_args_is_help=True, invoke_without_command=True)


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", is_eager=True, help="显示版本号")] = False,
):
    """住宅通风计算与校核。"""
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def version():
    """输出软件版本。"""
    typer.echo(__version__)


@app.command()
def run(case_path: Path, out: Annotated[Path, typer.Option("--out")]):
    """执行 YAML 算例，将 JSON 和 Markdown 写入 out 目录。"""
    case = load_case(case_path)
    if case.module == "co2":
        data = case.input
        generation = float(data["occupants"]) * float(data["co2_l_h_person"]) * 1e-3 / 3600
        result = {
            "flow_m3_s": co2_flow(
                generation,
                float(data["co2_outdoor_ppm"]) * 1e-6,
                float(data["co2_limit_ppm"]) * 1e-6,
            )
        }
        packs = {"JGJT440-2018": "2018"}
    else:
        result, packs = execute(case, case_path)
    data_files = {"co2_activity.yaml": activity_data_path()} if case.module == "ventrate" else {}
    if case.module in ("energy_erv", "energy_control", "vav_comparison"):
        from openresivent.energy.examples import weather_files

        data_files.update({f"{city}.epw": path for city, path in weather_files().items()})
    if case.module == "natural_cooling":
        from os import environ

        data_files["guangzhou.epw"] = Path(environ["ORV_WEATHER_DIR"]) / "guangzhou.epw"
    if case.module == "duct_network":
        data_files["duct_fittings.yaml"] = parameter_data_path("duct_fittings.yaml")
    if case.module == "health_pah":
        data_files["pah_tef.yaml"] = parameter_data_path("pah_tef.yaml")
        data_files["exposure_defaults.yaml"] = parameter_data_path("exposure_defaults.yaml")
    if case.module in ("tracer", "air_age") and "csv" in case.input:
        data_files[case.input["csv"]] = case_path.parent / case.input["csv"]
    output = {"id": case.meta.id, **result, "provenance": provenance(case_path, packs, data_files)}
    markdown = render(case.meta.title, case.module, case.input, result)
    parts = case_path.resolve().parts
    if "cases" in parts and "book" in parts and case_path.parent.name.startswith("ch"):
        from openresivent.report.book import render_book

        appendix = out / ".appendix"
        appendix.mkdir(parents=True, exist_ok=True)
        (appendix / f"{case.meta.id}.md").write_text(markdown, encoding="utf8")
        markdown = render_book(
            case.meta.title, case.meta.id, case_path.parent.name, markdown, result, case.input
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{case.meta.id}.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    (out / f"{case.meta.id}.md").write_text(markdown, encoding="utf8")


@app.command()
def report(
    case_path: Path,
    format: Annotated[str, typer.Option("--format")] = "docx",
    out: Annotated[Path, typer.Option("--out")] = Path("build/reports"),
    type: Annotated[str, typer.Option("--type")] = "design",
):
    """根据算例生成设计、竖井或验收运维报告。"""
    if format != "docx":
        raise typer.BadParameter("目前仅支持 docx")
    from openresivent.report.docx_report import generate

    case = load_case(case_path)
    if type == "design":
        path = generate(case_path, out / f"{case.meta.id}.docx")
    elif type in ("shaft", "commissioning"):
        from openresivent.report.special_reports import generate_special

        path = generate_special(case_path, out / f"{case.meta.id}.docx", type)
    else:
        raise typer.BadParameter("报告类型须为 design、shaft 或 commissioning")
    typer.echo(str(path))


@app.command()
def sweep(
    definition: Path,
    out: Annotated[Path, typer.Option("--out")],
    workers: Annotated[int, typer.Option("--workers")] = 1,
):
    """执行 YAML 参数扫描，结果写入指定本地目录并可断点续算。"""
    import yaml

    from openresivent.sweep import run_sweep

    spec = yaml.safe_load(definition.read_text(encoding="utf8"))
    base_path = (definition.parent / spec["base_case"]).resolve()
    base = yaml.safe_load(base_path.read_text(encoding="utf8"))
    typer.echo(json.dumps(run_sweep(spec, base, out, workers), ensure_ascii=False))


@app.command()
def desktop():
    """启动本机桌面窗口；缺少窗口组件时使用浏览器。"""
    from openresivent.desktop import desktop as launch

    launch()


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
):
    """启动本地 API；非本机监听需要用户显式指定。"""
    import uvicorn

    uvicorn.run("openresivent.api:app", host=host, port=port)


if __name__ == "__main__":
    app()
