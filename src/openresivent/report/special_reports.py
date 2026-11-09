"""高层竖井和调试运维专题报告；所有参数需项目复核。"""

from datetime import date
from pathlib import Path

from docx import Document

from openresivent.core.case import Case, load_case
from openresivent.core.provenance import provenance
from openresivent.core.runner import execute
from openresivent.dwelling.templates import acceptance_scenarios
from openresivent.recovery.selection import maintenance
from openresivent.report.docx_report import _flatten, _table, standard_name, validate_document
from openresivent.shaft.model import ShaftConfig, calculate


def _header(doc, case, prov, packs, title):
    doc.add_heading(title, 0)
    doc.add_paragraph("项目名称：" + case.meta.title)
    doc.add_paragraph("软件版本：" + prov["software_version"])
    doc.add_paragraph(
        "代码提交：" + prov["git_commit"] + ("（工作区有未提交修改）" if prov["git_dirty"] else "")
    )
    doc.add_paragraph(
        "规则包版本：" + ("、".join(standard_name(k) for k in packs) if packs else "本算例无规则包")
    )
    doc.add_paragraph("日期：" + date.today().isoformat())
    doc.add_paragraph("输入 SHA256：" + prov["input_sha256"])
    doc.add_page_break()
    doc.add_heading("输入参数及来源", 1)
    _table(
        doc,
        ["参数", "数值", "来源分级"],
        [(k, v, "输入数据，来源需确认") for k, v in _flatten(case.input)],
    )


def _shaft(doc, data):
    conf = ShaftConfig(**data["shaft"])
    shaft = calculate(conf)
    home_case = Case.model_validate(
        {
            "meta": {"id": "example", "title": "压差示例"},
            "module": "dwelling_pressure",
            "input": data["dwelling"],
        }
    )
    home, _ = execute(home_case, Path("."))
    doc.add_heading("竖井逐层风量与压力", 1)
    _table(
        doc,
        [
            "楼层",
            "油烟机状态",
            "排风量 m³/h",
            "相对同高度室外 Pa",
            "相对住户 Pa",
            "未运行倒灌 m³/h",
        ],
        [
            (
                str(f["floor"]),
                "运行" if f["active"] else "未运行",
                f"{f['exhaust_m3_s'] * 3600:.2f}",
                f"{f['shaft_to_outdoor_pa']:.2f}",
                f"{f['shaft_to_home_pa']:.2f}",
                f"{f['backflow_m3_s'] * 3600:.2f}",
            )
            for f in shaft["floors"]
        ],
    )
    bottom = shaft["bottom_meets_300"]
    doc.add_paragraph(
        "底层是否达到300 m³/h："
        + ("底层未运行，不判定" if bottom is None else "达到" if bottom else "未达到")
    )
    doc.add_heading("户内负压与补风方案对比", 1)
    labels = {
        "no_makeup": "无补风",
        "interlock": "联锁",
        "opening": "起居室自然补风",
        "opening_kitchen": "厨房自然补风",
        "mechanical_living": "起居室机械补风",
        "mechanical_kitchen": "厨房机械补风",
    }
    rows = []
    for n, scenarios in home["scenarios"].items():
        for mode, label in labels.items():
            x = scenarios[mode]
            p = x["pressures_pa"]["kitchen"]
            threshold = x["threshold_pa"]
            rows.append(
                (
                    n,
                    label,
                    f"{p:.2f}",
                    f"{threshold:.2f}",
                    "提示" if x["negative_pressure_warning"] else "未触发提示",
                )
            )
    _table(doc, ["n50 h⁻¹", "方案", "厨房相对室外 Pa", "负压提示阈值 Pa", "结果"], rows)
    doc.add_paragraph(
        "15 Pa为示例提示阈值，不是规范安全限值；高风险或倒灌工况建议开展专项论证。模型不代表实际楼宇测试。"
    )


def _commissioning(doc, data):
    d = data["acceptance"]
    m = data["maintenance"]
    if "records" in d:
        from openresivent.measure.acceptance import (
            continuous_monitor,
            design_window_judgement,
            flow_deviation,
            required_homes,
            spot_evaluate,
            track_judgement,
        )

        continuous = continuous_monitor(d["records"])
        tracks = track_judgement(continuous["indoor_pm"], continuous["indoor_co2"])
        tracks["design"] = design_window_judgement(d["records"])
        result = {
            "continuous": continuous,
            "tracks": tracks,
            "spot": spot_evaluate(d["spot_records"], retest_records=d.get("retest_records")),
            "total_flow": flow_deviation(
                d["total_design_m3_h"] / 3600, d["total_measured_m3_h"] / 3600
            ),
            "terminal_flow": flow_deviation(
                d["terminal_design_m3_h"] / 3600, d["terminal_measured_m3_h"] / 3600, terminal=True
            ),
            "required_homes": required_homes(d["total_homes"]),
        }
    else:
        a = Case.model_validate(
            {
                "meta": {"id": "measurement", "title": "验收数据"},
                "module": "acceptance_synthetic",
                "input": d,
            }
        )
        result, _ = execute(a, Path("."))
    core = maintenance(
        m["core"], initial_latent=m["initial_latent"], after_clean_latent=m["after_clean_latent"]
    )
    doc.add_heading("风量偏差与抽检", 1)
    for k, label in [("total_flow", "系统总风量"), ("terminal_flow", "末端风量")]:
        x = result[k]
        doc.add_paragraph(
            f"{label}偏差 {x['deviation'] * 100:.2f}%，限值 ±{x['limit'] * 100:.0f}%，{'满足' if x['passed'] else '不满足'}；依据 GB 55015-2021 第6.3.13条。"
        )
    doc.add_paragraph(
        f"样本户数建议：{result['required_homes']} 户。"
        + ("输入数据及现场条件须核实。" if "records" in d else "示例数据为合成，不能作为竣工证据。")
    )
    doc.add_heading("连续监测双轨与检测法", 1)
    continuous = result["continuous"]
    tracks = result["tracks"]
    spot = result["spot"]
    doc.add_paragraph("连续监测选取室外最不利五日：" + "、".join(continuous["selected_days"]))
    doc.add_paragraph(
        f"室内 PM2.5 平均 {continuous['indoor_pm'] * 1e9:.2f} μg/m³，CO₂ {continuous['indoor_co2'] * 1e6:.0f} ppm。"
    )
    for key, label in [
        ("design", "设计轨（PM2.5日均、CO₂小时均值）"),
        ("acceptance", "验收轨（最不利日统计）"),
    ]:
        x = tracks[key]
        doc.add_paragraph(
            f"{label}：PM2.5 {'满足' if x['pm25_passed'] else '不满足'}，CO₂ {'满足' if x['co2_passed'] else '不满足'}。"
        )
    status = {
        "passed": "满足",
        "failed": "不满足",
        "invalid_first": "首测时长不足",
        "invalid_retest": "复测时长不足",
        "retest_required": "需复测",
    }
    doc.add_paragraph(
        f"检测法：{status[spot['status']]}；首测至少45分钟，未达标须按要求复测；关闭门窗及运行条件须现场核实。"
    )
    doc.add_heading("联合验收工况清单", 1)
    _table(
        doc,
        ["工况", "共同测量项目"],
        [(x["name"], "、".join(x["measure"])) for x in acceptance_scenarios()],
    )
    doc.add_heading("滤网与芯体维护", 1)
    ratio = m["filter_pressure_ratio"]
    doc.add_paragraph(
        f"滤网压差与初始值比 {ratio:.2f}；达到2倍为研究建议的更换提示，{'建议核查并更换' if ratio >= 2 else '尚未达到提示值'}；并结合设备说明书和实测压差。"
    )
    doc.add_paragraph(core["method"])
    doc.add_paragraph(
        f"清洗后潜热效率相对衰减 {core['post_clean_decline'] * 100:.2f}%；{'建议考虑更换' if core['replace_recommended'] else '尚未达到示例更换阈值'}。该阈值为研究建议，不是强制条文。"
    )


def generate_special(case_path: Path, output: Path, kind: str) -> Path:
    """根据单一 YAML 和指定报告类型生成 DOCX，路径和单位按算例输入。"""
    case = load_case(case_path)
    if kind not in ("shaft", "commissioning") or case.module != "report_" + kind:
        raise ValueError("报告类型与算例不匹配")
    packs = (
        {"JGJT440-2018": "2018", "GB55015-2021": "2021", "GBT18883-2022": "2022"}
        if kind == "commissioning"
        else {}
    )
    prov = provenance(case_path, packs)
    doc = Document()
    _header(
        doc,
        case,
        prov,
        packs,
        "高层竖井防串烟与室内压差安全评估报告"
        if kind == "shaft"
        else "竣工调试、双轨验收与运维手册",
    )
    (_shaft if kind == "shaft" else _commissioning)(doc, case.input)
    doc.add_heading("适用范围与复核", 1)
    doc.add_paragraph(
        "输入参数及数据须依据真实项目、现场测试及相关标准复核；示例不代表实测，本报告不替代专项设计、产品认证或安全验收。"
    )
    validate_document(doc, reject_names=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    return output
