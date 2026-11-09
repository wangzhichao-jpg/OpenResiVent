"""可选本地词表；公开安装包不包含词表。"""

from pathlib import Path


def load_private_terms(path: Path | None = None) -> tuple[str, ...]:
    """读取逐行字面词；未安装词表时返回空元组。"""
    if path is None:
        path = Path(__file__).resolve().parents[3] / "tools/private/scan_terms.txt"
    if not path.is_file():
        return ()
    return tuple(
        line.strip()
        for line in path.read_text(encoding="utf8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
