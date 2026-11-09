"""两类专题报告的内容、生成和安全检查。"""

import re
from pathlib import Path

import pytest
from docx import Document
from typer.testing import CliRunner

from openresivent.cli import app
from openresivent.report.docx_report import document_text, validate_document
from openresivent.report.special_reports import generate_special

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "kind,file,terms",
    [
        (
            "shaft",
            "shaft_example.yaml",
            [
                "高层竖井防串烟与室内压差安全评估报告",
                "竖井逐层风量与压力",
                "相对同高度室外 Pa",
                "相对住户 Pa",
                "未运行倒灌",
                "底层是否达到300",
                "户内负压与补风方案对比",
                "建议开展专项论证",
            ],
        ),
        (
            "commissioning",
            "commissioning_example.yaml",
            [
                "竣工调试、双轨验收与运维手册",
                "风量偏差与抽检",
                "−7.50",
                "连续监测双轨与检测法",
                "设计轨",
                "验收轨",
                "检测法",
                "联合验收工况清单",
                "滤网与芯体维护",
                "研究建议",
            ],
        ),
    ],
)
def test_report(kind, file, terms, tmp_path):
    p = ROOT / "cases/reports" / file
    run = CliRunner().invoke(
        app, ["report", str(p), "--type", kind, "--format", "docx", "--out", str(tmp_path)]
    )
    assert run.exit_code == 0, run.exception
    docs = list(tmp_path.glob("*.docx"))
    assert len(docs) == 1
    doc = Document(docs[0])
    text = document_text(doc)
    validate_document(doc, reject_names=True)
    for t in terms:
        assert t.replace("−", "-") in text.replace("−", "-"), t
    assert not re.search(
        r"\u5de5\u4f5c\u6307\u4ee4|WO-|\u004d\u0053\u0047\u002d|(?:GBT|JGJT|GB)\d{3,}-\d{4}|有限公司|研究院|设计院|大学|学院|集团|协会",
        text,
    )
    assert "输入 SHA256" in text and "规则包版本" in text


def test_mismatch(tmp_path):
    p = ROOT / "cases/reports/shaft_example.yaml"
    with pytest.raises(ValueError):
        generate_special(p, tmp_path / "a.docx", "commissioning")
    run = CliRunner().invoke(app, ["report", str(p), "--type", "bad", "--out", str(tmp_path)])
    assert run.exit_code != 0


def test_actual_measurement_path(tmp_path):
    from datetime import datetime, timedelta

    import yaml

    p = ROOT / "cases/reports/commissioning_example.yaml"
    data = yaml.safe_load(p.read_text())
    d = data["input"]["acceptance"]
    start = datetime(2026, 1, 1)
    d["records"] = [
        {
            "time": (start + timedelta(minutes=10 * i)).isoformat(),
            "outdoor_pm": 100e-9 if i // 144 >= 25 else 30e-9,
            "indoor_pm": 40e-9,
            "indoor_co2": 0.0008,
        }
        for i in range(30 * 144)
    ]
    d["spot_records"] = [
        {
            "time": (start + timedelta(minutes=i)).isoformat(),
            "indoor_pm": 40e-9,
            "indoor_co2": 0.0008,
        }
        for i in range(46)
    ]
    f = tmp_path / "input.yaml"
    f.write_text(yaml.safe_dump(data, allow_unicode=True))
    output = generate_special(f, tmp_path / "measured.docx", "commissioning")
    text = document_text(Document(output))
    assert "4320 条记录" in text and "输入数据及现场条件须核实" in text
    assert "示例数据为合成" not in text


def test_name_rejected():
    d = Document()
    d.sections[0].footer.paragraphs[0].text = "某某科技有限公司"
    with pytest.raises(ValueError):
        validate_document(d, reject_names=True)
