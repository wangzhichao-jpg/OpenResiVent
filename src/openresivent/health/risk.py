"""健康风险计算，依据书稿 2.2 式 2-1、2-1a、2-2。"""


def teq(concentrations: dict[str, float], factors: dict[str, float]) -> float:
    """各组分质量浓度 kg/m³、无量纲 TEF → 等效浓度 kg/m³。"""
    if any(v < 0 for v in concentrations.values()) or any(v < 0 for v in factors.values()):
        raise ValueError("浓度和因子不得为负")
    return sum(value * factors[name] for name, value in concentrations.items())


def exposure_factor(
    hours_day: float, days_year: float, years: float, averaging_years: float
) -> float:
    """日暴露小时、年暴露天数、暴露年数、平均年数 → 无量纲暴露比例。"""
    if (
        not 0 <= hours_day <= 24
        or not 0 <= days_year <= 365
        or years < 0
        or averaging_years <= 0
        or years > averaging_years
    ):
        raise ValueError("暴露参数无效")
    return hours_day / 24 * days_year / 365 * years / averaging_years


def icr(concentration: float, unit_risk: float, factor: float) -> float:
    """浓度 kg/m³、吸入单位风险 (kg/m³)⁻¹、无量纲暴露比例 → 无量纲 ICR。"""
    if concentration < 0 or unit_risk < 0 or not 0 <= factor <= 1:
        raise ValueError("风险参数无效")
    return concentration * unit_risk * factor


def hazard_quotient(concentration: float, reference: float, factor: float = 1) -> float:
    """浓度及参考浓度 kg/m³、暴露比例 → 无量纲 HQ。"""
    if concentration < 0 or reference <= 0 or not 0 <= factor <= 1:
        raise ValueError("风险参数无效")
    return concentration * factor / reference


def chronic_daily_intake(
    concentration: float, inhalation_rate: float, body_mass: float, factor: float
) -> float:
    """浓度 kg/m³、连续暴露时呼吸率 m³/s、体重 kg、暴露比例 → CDI kg/(kg·s)。"""
    if concentration < 0 or inhalation_rate < 0 or body_mass <= 0 or not 0 <= factor <= 1:
        raise ValueError("暴露输入无效")
    return concentration * inhalation_rate * factor / body_mass


def dose_hazard_quotient(cdi: float, reference_dose: float) -> float:
    """剂量及参考剂量 kg/(kg·s) → 无量纲 HQ。"""
    if cdi < 0 or reference_dose <= 0:
        raise ValueError("剂量无效")
    return cdi / reference_dose


def lifetime_cancer_risk(cdi: float, slope_factor: float) -> float:
    """剂量 kg/(kg·s)、斜率因子 (kg·s)/kg → 无量纲致癌风险。"""
    if cdi < 0 or slope_factor < 0:
        raise ValueError("剂量或斜率无效")
    return cdi * slope_factor


def risk_category(risk: float) -> str:
    """无量纲致癌风险 → 风险类别，阈值依据书稿 2.2.1.2。"""
    if risk < 0:
        raise ValueError("风险不可为负")
    return "可忽略" if risk < 1e-6 else "潜在风险" if risk <= 1e-4 else "不可接受"
