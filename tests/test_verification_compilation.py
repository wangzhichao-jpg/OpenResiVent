"""验证报告汇编保留全部源文档及关键数值。"""

import importlib.util
from pathlib import Path

from docx import Document

spec = importlib.util.spec_from_file_location(
    "verification_report", Path(__file__).resolve().parents[1] / "tools/compile_verification.py"
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_compilation(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OUT", tmp_path)
    report.main()
    text = (tmp_path / "验证报告.md").read_text(encoding="utf8")
    for path in (Path(report.ROOT) / "docs/verification").glob("*.md"):
        assert f"### {path.stem}" in text
    for value in (
        "0.02337%",
        "1.610%",
        "0.00274%",
        "28.977 dB",
        "−0.023 dB",
        "36.0823%",
        "49.8624%",
    ):
        assert value in text
    doc = Document(tmp_path / "验证报告.docx")
    assert len(doc.tables) > 5
    assert any("验证报告" in p.text for p in doc.paragraphs)
