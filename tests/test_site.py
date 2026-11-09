"""文档站内容隔离与禁止用语检查。"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_site_navigation_and_redlines():
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text())
    assert config["docs_dir"] == "docs/site"
    assert len(config["nav"]) == 7
    files = list((ROOT / "docs/site").rglob("*.md"))
    assert len(files) >= 5
    for p in files:
        text = p.read_text()
        assert not re.search(
            r"\u5de5\u4f5c\u6307\u4ee4|WO-|\u004d\u0053\u0047\u002d|\u7ba1\u7406\u7aef|(?:GBT|JGJT|GB)\d{3,}-\d{4}|有限公司|研究院|大学|企业品牌",
            text,
        ), p
