"""健康风险输入层单位换算。"""


def iur_per_ug_m3_to_per_kg_m3(value: float) -> float:
    """吸入单位风险 (μg/m³)⁻¹ → (kg/m³)⁻¹；1 kg = 10⁹ μg。"""
    if value < 0:
        raise ValueError("单位风险不能为负")
    return value * 1e9
