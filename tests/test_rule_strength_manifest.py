"""规则强度表应覆盖公开包的全部条目。"""

from pathlib import Path

from openresivent.rules.engine import load_pack

ROOT = Path(__file__).resolve().parents[1]


def test_rule_strength_document_covers_all_rules():
    doc = (ROOT / "docs/theory/规则强度核对.md").read_text(encoding="utf8")
    for path in (ROOT / "src/openresivent/rules/packs").glob("*.yaml"):
        pack = load_pack(path)
        for rule in pack["rules"]:
            assert rule["id"] in doc
            assert f"| {rule['strength']} |" in doc
