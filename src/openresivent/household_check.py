"""一户校核：组合既有模块，不引入新的计算模型。"""

import json
import re
from decimal import Decimal
from pathlib import Path

from docx import Document
from pydantic import BaseModel, ConfigDict, Field

from openresivent import __version__
from openresivent.core.case import Case
from openresivent.core.runner import execute
from openresivent.report.docx_report import _table as _base_table
from openresivent.report.docx_report import validate_document


class HouseholdCheck(BaseModel):
    """一户输入；各子算例沿用其原有单位与规则包。"""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    ventilation: Case
    dwelling: Case
    sources: dict[str, str] = Field(default_factory=dict)


def calculate(data: HouseholdCheck) -> dict:
    """复用新风、户内压差、最小补风及可选噪声模块，返回原始 SI 结果。"""
    if data.ventilation.module != "ventrate" or data.dwelling.module != "dwelling_pressure":
        raise ValueError("算例模块必须分别为全户新风和户内压差")
    vent, vp = execute(data.ventilation, Path("case.yaml"))
    dwelling, dp = execute(data.dwelling, Path("case.yaml"))
    d = data.dwelling.input
    if len(data.ventilation.input["bedrooms"]) != d["bedrooms"]:
        raise ValueError("卧室数量不一致，请核对户型")
    inverse = {}
    for n50 in d["n50_per_h"]:
        inverse_case = Case.model_validate(
            {
                "meta": {"id": "inverse", "title": "补风反算", "rules": []},
                "module": "makeup_design",
                "input": {
                    "bedrooms": d["bedrooms"],
                    "volume_m3": d["volume_m3"],
                    "n50_per_h": n50,
                    "hood_m3_h": d["hood_m3_h"],
                    "fresh_supply_m3_h": d["fresh_supply_m3_h"],
                    "fresh_exhaust_m3_h": d["fresh_exhaust_m3_h"],
                    "threshold_pa": d["threshold_pa"],
                },
            }
        )
        inverse[str(n50)], _ = execute(inverse_case, Path("case.yaml"))
    checks = list(vent.get("checks", []))
    checks.extend(vent.get("noise", {}).get("checks", []))
    return {
        "ventilation": vent,
        "dwelling": dwelling,
        "inverse": inverse,
        "checks": checks,
        "rule_packs": {**vp, **dp},
        "software_version": __version__,
    }


ROOM_NAMES = {
    "living": "起居室",
    "kitchen": "厨房",
    "bath": "卫生间",
    **{f"bed{i}": f"卧室{i}" for i in range(1, 5)},
}
SCENARIO_NAMES = {
    "no_makeup": "无补风",
    "interlock": "联锁",
    "opening": "起居室自然补风",
    "opening_kitchen": "厨房自然补风",
    "mechanical_living": "起居室机械补风",
    "mechanical_kitchen": "厨房机械补风",
}
METHODS = {"A": "换气次数法", "B": "人员法", "C": "二氧化碳法", "D": "甲醛法"}


def _source(data: HouseholdCheck, path: str, *, standard: bool = False) -> str:
    """用户输入优先；仅已知数值及适用规则包满足时标注标准。"""
    if data.sources.get(path) == "用户输入":
        return "用户输入"
    if path == "dwelling_pressure.density_kg_m3":
        return "通用参数"
    if standard:
        return "GB/T 18883-2022 第4.2条、表1"
    return "示例值，需用户确认"


def _one(value):
    rounded = f"{value:.1f}"
    return "0.0" if rounded == "-0.0" else rounded


def _flow(value):
    return "未启用" if value is None else _one(value * 3600)


def _methods(row):
    chosen = row.get("selected")
    if chosen is None:
        available = [x for x in (row.get("A"), row.get("B"), row.get("D")) if x is not None]
        chosen = max(available) if available else None
    names = [
        name
        for key, name in METHODS.items()
        if row.get(key) is not None and chosen is not None and abs(row[key] - chosen) <= 1e-12
    ]
    return chosen, "、".join(names) or "未确定"


def _table(doc, headers, rows):
    """沿用既有表格版式，跨页时重复表头并避免拆分数据行。"""
    from docx.oxml import OxmlElement
    from docx.shared import Inches

    table = _base_table(doc, headers, rows)
    for i, row in enumerate(table.rows):
        props = row._tr.get_or_add_trPr()
        props.append(OxmlElement("w:cantSplit"))
        if i == 0:
            props.append(OxmlElement("w:tblHeader"))
    if headers == ["参数", "数值", "单位", "来源分级"]:
        table.autofit = False
        for column, width in zip(table.columns, (1.8, 0.8, 0.8, 2.8), strict=True):
            column.width = Inches(width)
            for cell in column.cells:
                cell.width = Inches(width)
    return table


def _validate_readable(doc):
    from openresivent.report.docx_report import document_text

    text = document_text(doc)
    # 仅检查正文输出；完整结果由单独 JSON 提供，不藏在文档中。
    if re.search(
        r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b|\b[A-Za-z][A-Za-z0-9_]*(?:\[\d+\]|\.[A-Za-z_])|\b\d+(?:\.\d+)?[eE][+-]\d+\b",
        text,
    ):
        raise ValueError("报告正文包含内部字段路径或程序科学计数法")


def save_report(data: HouseholdCheck, result: dict, output: Path) -> Path:
    """生成工程单位的合并报告；完整精度结果另见 JSON。"""
    from docx.enum.text import WD_COLOR_INDEX
    from docx.shared import RGBColor

    doc = Document()
    doc.add_heading("住宅通风一户校核报告", 0)
    doc.add_paragraph("项目名称：" + data.title)
    doc.add_paragraph("软件版本：" + result["software_version"])
    doc.add_paragraph("计算结果用于设计自查，不替代现场检测、安全评估或设计审查。")
    doc.add_paragraph("完整精度计算结果另见独立 JSON 文件；本报告数值按工程精度显示。")
    doc.add_page_break()
    doc.add_heading("输入参数及来源", 1)
    v, d = data.ventilation.input, data.dwelling.input
    rows = []

    def add(label, value, unit, path, standard=False):
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            value = format(Decimal(str(value)), "f")
        rows.append((label, value, unit, _source(data, path, standard=standard)))

    v_display = dict(v)
    v_display.setdefault("occupants", v.get("default_occupants", 3.2))
    for key, default in (("outdoor_ppm", 400), ("limit_ppm", 1000), ("allowance", 0.05)):
        v_display.setdefault(key, default)
    active_rules = data.ventilation.meta.rules or ["JGJT440-2018", "GBT18883-2022"]
    for key, label, unit in (
        ("area_m2", "居住面积", "m²"),
        ("floor_area_m2", "建筑面积", "m²"),
        ("height_m", "净高", "m"),
        ("occupants", "设计人数", "人"),
        ("outdoor_ppm", "室外二氧化碳浓度", "ppm"),
        ("limit_ppm", "室内二氧化碳浓度限值", "ppm"),
        ("allowance", "风机风量附加率", "—"),
    ):
        if key in v_display:
            add(
                label,
                v_display[key],
                unit,
                f"ventrate.{key}",
                standard=key == "limit_ppm"
                and v_display[key] == 1000
                and bool({"GBT18883-2022", "GB/T 18883-2022"} & set(active_rules)),
            )
    for i, room in enumerate(v["bedrooms"], 1):
        for key, label, unit in (
            ("area_m2", "面积", "m²"),
            ("height_m", "净高", "m"),
            ("occupants", "人数", "人"),
        ):
            add(f"卧室{i}{label}", room[key], unit, f"ventrate.bedrooms[{i}].{key}")
        if "activity" in room:
            activity = {"sleeping": "睡眠", "sedentary": "静坐", "light": "轻活动"}.get(
                room["activity"], "其他活动，详见算例"
            )
            add(f"卧室{i}活动状态", activity, "—", f"ventrate.bedrooms[{i}].activity")
        for j, material in enumerate(room.get("hcho_materials", []), 1):
            add(
                f"卧室{i}材料{j}散发率",
                material["ef_mg_m2_h"],
                "mg/(m²·h)",
                f"ventrate.bedrooms[{i}].hcho_materials[{j}].ef_mg_m2_h",
            )
            add(
                f"卧室{i}材料{j}面积",
                material["area_m2"],
                "m²",
                f"ventrate.bedrooms[{i}].hcho_materials[{j}].area_m2",
            )
    for key, label in (("area_m2", "面积"), ("height_m", "净高")):
        if key in v["living"]:
            add(
                f"起居室{label}",
                v["living"][key],
                "m²" if key == "area_m2" else "m",
                f"ventrate.living.{key}",
            )
    for key, label, unit in (
        ("volume_m3", "住宅体积", "m³"),
        ("hood_m3_h", "油烟机风量", "m³/h"),
        ("fresh_supply_m3_h", "新风送风量", "m³/h"),
        ("fresh_exhaust_m3_h", "新风排风量", "m³/h"),
        ("mechanical_makeup_m3_h", "机械补风量", "m³/h"),
        ("threshold_pa", "负压提示值", "Pa"),
        ("density_kg_m3", "空气密度", "kg/m³"),
    ):
        if key in d:
            add(label, d[key], unit, f"dwelling_pressure.{key}")
    add(
        "自然补风口有效面积",
        f"{d['opening_area_m2'] * 10000:.0f}",
        "cm²",
        "dwelling_pressure.opening_area_m2",
    )
    for key, label in (
        ("door_gap_area_m2", "门缝有效面积"),
        ("transfer_area_m2", "过流口有效面积"),
    ):
        if key in d:
            add(label, f"{d[key] * 10000:.0f}", "cm²", f"dwelling_pressure.{key}")
    if "kitchen_open" in d:
        add(
            "厨房状态",
            "开放" if d["kitchen_open"] else "封闭",
            "—",
            "dwelling_pressure.kitchen_open",
        )
    for key, label in (
        ("hood_room", "油烟机位置"),
        ("supply_room", "新风送风位置"),
        ("exhaust_room", "新风排风位置"),
        ("bath_fan_room", "卫生间风机位置"),
    ):
        if key in d:
            add(label, ROOM_NAMES.get(d[key], "其他房间"), "—", f"dwelling_pressure.{key}")
    for i, value in enumerate(d["n50_per_h"], 1):
        add(f"气密性方案{i}", value, "次/h", f"dwelling_pressure.n50_per_h[{i}]")
    _table(doc, ["参数", "数值", "单位", "来源分级"], rows)
    doc.add_heading("各房间新风量", 1)
    rows = []
    for i, row in enumerate(result["ventilation"]["bedrooms"], 1):
        selected, names = _methods(row)
        rows.append((f"卧室{i}", *(_flow(row.get(k)) for k in METHODS), _flow(selected), names))
    row = result["ventilation"]["living"]
    selected, names = _methods(row)
    rows.append(("起居室", *(_flow(row.get(k)) for k in METHODS), _flow(selected), names))
    _table(
        doc,
        [
            "房间",
            "换气次数法 m³/h",
            "人员法 m³/h",
            "二氧化碳法 m³/h",
            "甲醛法 m³/h",
            "采用 m³/h",
            "取大值来源",
        ],
        rows,
    )
    vresult = result["ventilation"]
    _table(
        doc,
        ["全户计算路径", "风量 m³/h"],
        [
            ("房间合计", _flow(vresult["room_total"])),
            ("全户换气次数法", _flow(vresult["whole_A"])),
            ("全户人员法", _flow(vresult["whole_B"])),
            ("全户甲醛法", _flow(vresult["whole_D"])),
            ("全户设计风量", _flow(vresult["design"])),
            ("风机选型风量", _flow(vresult["fan"])),
        ],
    )
    sources = [
        ("房间合计", vresult["room_total"]),
        ("全户换气次数法", vresult["whole_A"]),
        ("全户人员法", vresult["whole_B"]),
        ("全户甲醛法", vresult["whole_D"]),
    ]
    chosen = "、".join(
        name
        for name, value in sources
        if value is not None and abs(value - vresult["design"]) <= 1e-12
    )
    doc.add_paragraph("全户设计风量取大值来源：" + (chosen or "需核对"))
    doc.add_heading("户内压力与补风方案", 1)
    doc.add_paragraph("门两侧压差以起居室压力减去相应房间压力，正值表示起居室压力较高。")
    doc.add_paragraph("15 Pa 为示例提示值，不是燃气安全限值；实际判定按所设提示值进行。")
    summary = []
    for n, scenarios in result["dwelling"]["scenarios"].items():
        for name, entry in scenarios.items():
            summary.append(
                (
                    format(Decimal(str(n)), "f"),
                    SCENARIO_NAMES.get(name, "其他方案"),
                    _one(entry["pressures_pa"]["kitchen"]),
                    _one(entry["threshold_pa"]),
                    "警示：超过提示值" if entry["negative_pressure_warning"] else "未超过提示值",
                )
            )
    table = _table(doc, ["气密性 次/h", "补风方案", "厨房压力 Pa", "提示值 Pa", "提示"], summary)
    for row, values in zip(table.rows[1:], summary, strict=True):
        if values[-1].startswith("警示"):
            for run in row.cells[-1].paragraphs[0].runs:
                run.bold = True
                run.font.color.rgb = RGBColor(0xB0, 0, 0)
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    for n, scenarios in result["dwelling"]["scenarios"].items():
        for name, entry in scenarios.items():
            doc.add_heading(
                f"气密性 {format(Decimal(str(n)), 'f')} 次/h：{SCENARIO_NAMES.get(name, '其他方案')}",
                2,
            )
            pressure_rows = [
                (ROOM_NAMES.get(room, "其他房间"), _one(pressure))
                for room, pressure in entry["pressures_pa"].items()
            ]
            _table(doc, ["房间", "相对室外压力 Pa"], pressure_rows)
            door_rows = [
                (ROOM_NAMES.get(room, "其他房间") + "门", _one(value["delta_p_pa"]))
                for room, value in entry["doors"].items()
            ]
            _table(doc, ["门", "两侧压差 Pa"], door_rows or [("无", "—")])
    doc.add_heading("最小补风量反算", 1)
    doc.add_paragraph(
        "反算采用封闭厨房、默认门缝及过流口、起居室送风、厨房补风；与自选前向工况可能不同。"
    )
    _table(
        doc,
        ["气密性 次/h", "最小机械补风 m³/h", "最小自然补风有效面积 cm²"],
        [
            (
                format(Decimal(str(n)), "f"),
                _flow(x["mechanical"]["value"]),
                f"{x['opening']['value'] * 10000:.0f}",
            )
            for n, x in result["inverse"].items()
        ],
    )
    if "noise" in vresult:
        doc.add_heading("卧室噪声初筛", 1)
        _table(
            doc,
            ["风量 m³/h", "A声级 dB(A)", "判断"],
            [
                (
                    _one(row["flow_m3_s"] * 3600),
                    _one(row["a_weighted_db"]),
                    "满足" if check["passed"] else "不满足",
                )
                for row, check in zip(
                    vresult["noise"]["settings"], vresult["noise"]["checks"], strict=True
                )
            ],
        )
        doc.add_paragraph("声学输入为示例假设，不替代产品或现场测量。")
    doc.add_heading("条文校核汇总", 1)
    labelled = []
    bedroom_number = 0
    for item in result["checks"]:
        label = ""
        if item.get("id") == "JGJT440-2018:4.2.2":
            bedroom_number += 1
            label = f"卧室{bedroom_number}："
        labelled.append((item, label))
    for strength in ("应", "宜", "其他"):
        doc.add_heading(strength, 2)
        rows = [
            (
                item.get("explanation", ""),
                label + item.get("requirement", ""),
                "满足" if item.get("passed") else "不满足",
            )
            for item, label in labelled
            if item.get("strength", "") == strength
            or (strength == "其他" and item.get("strength", "") not in ("应", "宜"))
        ]
        _table(doc, ["依据", "要求", "判断"], rows or [("无", "未配置", "不作判定")])
    output.parent.mkdir(parents=True, exist_ok=True)
    validate_document(doc)
    _validate_readable(doc)
    doc.save(output)
    return output


def result_json(result: dict) -> str:
    """将结果编码为可交换 JSON。"""
    return json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
