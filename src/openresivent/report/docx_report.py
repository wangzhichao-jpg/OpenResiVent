"""设计计算及条文合规自查报告；仅支持已验证的两个算例模块。"""

import re
from datetime import date
from pathlib import Path

from docx import Document

from openresivent.core.case import load_case
from openresivent.core.private_terms import load_private_terms
from openresivent.core.provenance import activity_data_path, provenance
from openresivent.core.runner import execute
from openresivent.report.markdown import render


def _flatten(value, path=""):
    """扁平化输入，不将来源字符串中的内部标记写入报告。"""
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("records", "spot_records", "retest_records") and isinstance(v, list):
                yield (f"{path}.{k}" if path else k), f"{len(v)} 条记录，完整数据见输入文件"
            elif k not in ("source", "assumption", "assumptions"):
                yield from _flatten(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for i, v in enumerate(value, 1):
            yield from _flatten(v, f"{path}[{i}]")
    else:
        yield path, str(value)


def _clean(text):
    text = str(text)
    for term in load_private_terms():
        text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:GBT|JGJT|GB)\d{3,}-\d{4}:[\w.:-]+", "", text)
    return text


def standard_name(pack: str) -> str:
    """将内部规则包标识转换为公开标准编号。"""
    match = re.fullmatch(r"(JGJT|GBT|GB)(\d+)-(\d{4})", pack)
    if not match:
        raise ValueError("未知的标准编号格式")
    prefix = {"JGJT": "JGJ/T", "GBT": "GB/T", "GB": "GB"}[match.group(1)]
    return f"{prefix} {match.group(2)}-{match.group(3)}"


def document_text(doc) -> str:
    """提取正文、嵌套表格、所有页眉页脚的可见文字。"""
    from docx.oxml.ns import qn

    bodies = [doc._element.body]
    for section in doc.sections:
        bodies.extend(
            x._element
            for x in (
                section.header,
                section.footer,
                section.first_page_header,
                section.first_page_footer,
                section.even_page_header,
                section.even_page_footer,
            )
        )
    return "\n".join("".join(node.itertext()) for body in bodies for node in body.iter(qn("w:p")))


def validate_document(doc, *, reject_names: bool = False) -> None:
    """扫描全部可见段落、表格、页眉页脚；违禁内容禁止交付。"""
    text = document_text(doc)
    if any(term.casefold() in text.casefold() for term in load_private_terms()) or re.search(
        r"(?:GBT|JGJT|GB)\d{3,}-\d{4}", text
    ):
        raise ValueError("报告含管理用语或内部规则编号")
    if reject_names and re.search(
        r"[\u4e00-\u9fffA-Za-z]{2,}(?:有限公司|股份公司|研究院|设计院|大学|学院|集团|协会|品牌)",
        document_text(doc),
    ):
        raise ValueError("报告疑似包含机构名称或品牌")


def _table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, headers, strict=True):
        cell.text = str(text)
    for row in rows:
        cells = table.add_row().cells
        for cell, text in zip(cells, row, strict=True):
            cell.text = _clean(text)
    return table


def generate(case_path: Path, output: Path) -> Path:
    """YAML 算例路径、输出路径 → DOCX；计算仍使用 SI。"""
    case = load_case(case_path)
    if case.module not in ("ventrate", "dwelling_pressure"):
        raise ValueError("当前自查报告仅支持全户新风量和户内压差算例")
    result, packs = execute(case, case_path)
    data_files = {"co2_activity.yaml": activity_data_path()} if case.module == "ventrate" else {}
    prov = provenance(case_path, packs, data_files)
    doc = Document()
    doc.add_heading("设计计算及条文合规自查报告", 0)
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
    if data_files:
        doc.add_paragraph("通用数据 SHA256：" + str(prov["data_sha256"]))
    doc.add_page_break()
    doc.add_heading("输入参数及来源", 1)
    _table(
        doc,
        ["输入参数", "数值", "来源分级"],
        [(k, v, "假设，需作者确认") for k, v in _flatten(case.input)],
    )
    doc.add_heading("演算过程", 1)
    text = render(case.meta.title, case.module, case.input, result)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("|"):
            continue
        line = line.replace("**", "").replace("$$", "").replace("$", "")
        doc.add_paragraph(_clean(line))
    if case.module == "dwelling_pressure":
        for n, scenarios in result["scenarios"].items():
            for label, entry in scenarios.items():
                doc.add_paragraph(
                    f"气密性 n50={n} h⁻¹；方案 {label}：厨房压力 {entry['pressures_pa']['kitchen']:.2f} Pa，起居室压力 {entry['pressures_pa']['living']:.2f} Pa。"
                )
    doc.add_heading("条文校核", 1)
    rows = []
    for check in result.get("checks", []):
        source = check.get("explanation", "").split("，")[0]
        rows.append(
            (
                source,
                check.get("strength", "—"),
                check.get("requirement", "—"),
                str(check.get("value", "—")),
                str(check.get("limit", "—")),
                "满足" if check.get("passed") else "不满足",
            )
        )
    if not rows:
        rows = [("不适用", "—", "本算例未配置条文判定", "—", "—", "不作规范合规结论")]
    _table(doc, ["条文号", "强度", "要求", "计算值（SI）", "限值（SI）", "结论"], rows)
    doc.add_heading("风险提示", 1)
    doc.add_paragraph(
        "模型结果仅用于设计自查，依赖输入及模型假设，不替代现场检测、法定审查或产品认证。"
    )
    if case.module == "dwelling_pressure":
        doc.add_paragraph(
            "设定压差阈值为示例条件，不是燃气安全限值；实际排烟及补风安全需现场评估。"
        )
    doc.add_heading("参数来源说明", 1)
    doc.add_paragraph(
        "本报告输入列为假设，需用户确认；活动参数等通用参数引用软件数据表及其来源。设计者应替换为实测或经确认的项目输入，并复核标准适用性。"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    validate_document(doc)
    doc.save(output)
    return output
