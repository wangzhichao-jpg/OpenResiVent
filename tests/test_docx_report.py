"""自查报告生成、重开和红线扫描。"""

import re
from pathlib import Path

import pytest
from docx import Document
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.report.docx_report import document_text, generate, validate_document

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("chapter,case", [("ch02", "ex2-03"), ("ch05", "ex5-07")])
def test_report(tmp_path, chapter, case):
    path = ROOT / "cases/book" / chapter / (case + ".yaml")
    r = CliRunner().invoke(app, ["report", str(path), "--format", "docx", "--out", str(tmp_path)])
    assert r.exit_code == 0, r.exception
    doc = Document(tmp_path / (case + ".docx"))
    text = document_text(doc)
    validate_document(doc)
    for term in (
        "设计计算及条文合规自查报告",
        "软件版本",
        "代码提交",
        "规则包版本",
        "输入 SHA256",
        "条文校核",
        "来源分级",
        "计算值（SI）",
        "风险提示",
    ):
        assert term in text
    assert not re.search(r"合成禁词|(?:GBT|JGJT|GB)\d{3,}-\d{4}", text)
    if case == "ex5-07":
        assert "不作规范合规结论" in text and "不是燃气安全限值" in text
    else:
        assert "JGJ/T 440-2018" in text and "GB/T 18883-2022" in text and "满足" in text


def test_scan_all_parts(monkeypatch):
    monkeypatch.setattr('openresivent.report.docx_report.load_private_terms', lambda: ('合成禁词',))
    for location in ("body", "table", "header", "footer"):
        doc = Document()
        if location == "body":
            doc.add_paragraph("JGJT440-2018")
        elif location == "table":
            doc.add_table(rows=1, cols=1).cell(0, 0).text = "合成禁词"
        elif location == "header":
            doc.sections[0].header.paragraphs[0].text = "合成禁词"
        else:
            doc.sections[0].footer.paragraphs[0].text = "GBT18883-2022"
        with pytest.raises(ValueError):
            validate_document(doc)


def test_unsupported(tmp_path):
    p = ROOT / "cases/book/ch06/ex6-06.yaml"
    with pytest.raises(ValueError):
        generate(p, tmp_path / "x.docx")
    r = CliRunner().invoke(app, ["report", str(p), "--format", "pdf", "--out", str(tmp_path)])
    assert r.exit_code != 0
