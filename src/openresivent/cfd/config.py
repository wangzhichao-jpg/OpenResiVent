"""外部流体计算的本地配置。"""

import os
from pathlib import Path


def case_root() -> Path:
    """返回案例和结果允许使用的根目录；不会创建目录。"""
    configured = os.environ.get("ORV_CFD_DIR")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (Path.home() / ".local/share/openresivent/cfd").resolve()
    )
