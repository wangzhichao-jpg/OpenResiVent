"""算例输入模型；输入参数的单位由具体模块定义。"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from openresivent.core.module_names import ALIASES, canonical


class Meta(BaseModel):
    """算例元数据，不涉及物理单位。"""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    title: str
    book_ref: str | None = None
    rules: list[str] = Field(default_factory=list)

    @field_validator("rules", mode="before")
    @classmethod
    def normalize_rules(cls, values):
        """对外标准编号转换为规则包标识。"""
        if not isinstance(values, list):
            return values
        mapping = {
            "JGJ/T 440-2018": "JGJT440-2018",
            "GB/T 18883-2022": "GBT18883-2022",
            "GB/T 51350-2019": "GBT51350-2019",
            "GB/T 21087-2020": "GBT21087-2020",
            "GB 50736-2012": "GB50736-2012",
        }
        return [mapping.get(x, x) if isinstance(x, str) else x for x in values]


class Case(BaseModel):
    """书稿方案 7.1 的输入格式；input 内的单位由各模块约定。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    meta: Meta
    module: str = Field(description="计算模块：co2、ventrate、tracer 或 network")
    input: dict[str, Any] = Field(description="模块输入；字段及单位由 module 对应格式确定")
    output: dict[str, Any] = Field(default_factory=dict)

    @field_validator("module", mode="before")
    @classmethod
    def normalize_module(cls, value):
        """保留旧名称一个版本，并提示弃用。"""
        if isinstance(value, str) and value in ALIASES:
            import warnings

            warnings.warn(
                f"模块 {value} 已弃用，请改用 {canonical(value)}", FutureWarning, stacklevel=2
            )
            return canonical(value)
        return value


def load_case(path: Path) -> Case:
    """读取 YAML 算例；path 为文件路径，返回经过验证的算例。"""
    with path.open(encoding="utf-8") as stream:
        return Case.model_validate(yaml.safe_load(stream))
