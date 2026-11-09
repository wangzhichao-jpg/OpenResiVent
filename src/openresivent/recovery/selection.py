"""热回收分档校核与维护建议。"""

from openresivent.core.runner import load_rules
from openresivent.rules.engine import check_rule


def assess(
    profile: str,
    *,
    sensible_heat: float,
    sensible_cool: float,
    total_heat: float,
    total_cool: float,
    specific_power: float,
    equipment_type: str = "sensible",
) -> dict:
    """档位、设备类型、效率 0–1、单位耗功率 W/(m³/s) → 分项初筛。"""
    values = (sensible_heat, sensible_cool, total_heat, total_cool)
    if (
        any(not 0 <= x <= 1 for x in values)
        or specific_power < 0
        or equipment_type not in ("sensible", "total")
    ):
        raise ValueError("效率或单位耗功率无效")
    if profile == "general":
        rules, versions = load_rules(["GBT21087-2020"])
        pairs = (
            [
                ("GBT21087-2020:sensible_heat", sensible_heat),
                ("GBT21087-2020:sensible_cool", sensible_cool),
            ]
            if equipment_type == "sensible"
            else [
                ("GBT21087-2020:total_heat", total_heat),
                ("GBT21087-2020:total_cool", total_cool),
            ]
        )
    elif profile == "near_zero":
        rules, versions = load_rules(["GBT51350-2019"])
        # 严寒/夏季具体适用工况需另按标准及产品类别复核。
        metric = (
            ("GBT51350-2019:6.2.7:sensible", sensible_heat)
            if equipment_type == "sensible"
            else ("GBT51350-2019:6.2.7:total", total_heat)
        )
        pairs = [metric, ("GBT51350-2019:6.2.8:sfp", specific_power / 3600)]
    else:
        raise ValueError("未知住宅档位")
    checks = [check_rule(rules[k], value) for k, value in pairs]
    return {
        "profile": profile,
        "equipment_type": equipment_type,
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
        "rule_versions": versions,
        "note": "仅按所给指标初筛；额定工况、产品类别及其余条文另行核验。",
    }


def maintenance(core: str, *, initial_latent: float, after_clean_latent: float) -> dict:
    """芯体类型、初始及清洗后潜热效率（0–1）→ 更换建议；书稿4.4.2。"""
    if (
        core not in ("paper", "cellulose")
        or not 0 < initial_latent <= 1
        or not 0 <= after_clean_latent <= 1
    ):
        raise ValueError("芯体类型或效率无效")
    loss = (initial_latent - after_clean_latent) / initial_latent
    return {
        "core": core,
        "post_clean_decline": loss,
        "replace_recommended": loss > 0.2,
        "method": "断电后表面低吸力吸尘；未经设备说明书许可不得水洗"
        if core == "paper"
        else "断电后按设备许可用温水轻柔冲洗，自然晾干；严禁高压水枪",
        "source": "书稿4.4.2 的研究建议；运维过程参照 JG/T 400-2025 并核查产品说明。具体清洗及更换阈值并非在此宣称为标准强制条文。",
    }
