"""公开模块名称及一个版本的旧名称兼容映射。"""

ALIASES = {
    "p2_dwelling": "dwelling_pressure",
    "p2_fan": "fan_curve",
    "p2_infiltration": "infiltration",
    "p303_ductless": "ductless",
    "p303_vav": "vav_comparison",
    "p303_guangzhou": "natural_cooling",
    "p3_natural": "natural_ventilation",
    "p3_jet": "air_jet",
    "p3_stack": "stack_ventilation",
    "p3_cap": "turbine_cowl",
    "p3_intake": "outdoor_intake",
    "m4_frost": "recovery_frost",
    "m4_fouling": "recovery_fouling",
    "m4_assess": "recovery_assess",
    "m4_maintenance": "recovery_maintenance",
}


def canonical(name: str) -> str:
    """旧模块名映射为公开名称。"""
    return ALIASES.get(name, name)


def internal(name: str) -> str:
    """公开名称映射到内部实现名称。"""
    return {v: k for k, v in ALIASES.items()}.get(name, name)
