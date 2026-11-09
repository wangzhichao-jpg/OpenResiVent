"""声明式比较规则，禁止执行任意表达式。"""

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Decision:
    """规则判定；数值和限值的单位取对应规则包说明。"""

    id: str
    strength: str
    requirement: str
    value: float
    limit: object
    passed: bool
    explanation: str


def load_pack(path: Path) -> dict:
    """读取并验证 YAML 规则包，path 是文件路径，返回规则包。"""
    with path.open(encoding="utf8") as stream:
        pack = yaml.safe_load(stream)
    if not isinstance(pack, dict) or not all(k in pack for k in ("id", "version", "rules")):
        raise ValueError("规则包缺少 id、version 或 rules")
    for rule in pack["rules"]:
        if not all(
            k in rule for k in ("id", "title", "strength", "params", "check", "source")
        ) or rule["strength"] not in ("应", "宜", "可"):
            raise ValueError("规则字段不完整或强度不合法")
    return pack


def check_rule(rule: dict, value: float, *, calculated_limit: float | None = None) -> dict:
    """按照规则比较数值 value，数值单位由规则定义，返回可序列化判定。"""
    check = rule["check"]
    op = check["op"]
    limit = check["limit"] if calculated_limit is None else calculated_limit
    if limit is None:
        raise ValueError("动态限值须由调用方计算并提供")
    if op == "min":
        passed = value >= limit
    elif op == "max":
        passed = value <= limit
    elif op == "range":
        passed = limit[0] <= value <= limit[1]
    else:
        raise ValueError("不支持的比较方式")
    return asdict(
        Decision(rule["id"], rule["strength"], rule["title"], value, limit, passed, rule["source"])
    )
