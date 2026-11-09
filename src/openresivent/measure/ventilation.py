"""通风测试基本方法；依据书稿 6.1、6.3。"""


def tracer_flow(injection: float, indoor: float, outdoor: float) -> float:
    """示踪物注入 kg/s 与室内外质量浓度 kg/m³ → 风量 m³/s。"""
    if injection < 0 or outdoor < 0 or indoor <= outdoor:
        raise ValueError("注入量或浓度无效")
    return injection / (indoor - outdoor)


def average_air_age(ages: list[float], volumes: list[float]) -> float:
    """各点局部空气龄 s、对应代表体积 m³ → 体积加权平均空气龄 s。"""
    if (
        not ages
        or len(ages) != len(volumes)
        or any(x < 0 for x in ages)
        or any(x <= 0 for x in volumes)
    ):
        raise ValueError("空气龄或代表体积无效")
    return sum(a * v for a, v in zip(ages, volumes, strict=True)) / sum(volumes)


def air_change_efficiency(nominal_age: float, average_age: float) -> float:
    """名义空气龄 s、体积加权平均空气龄 s → 无量纲换气效率。"""
    if nominal_age <= 0 or average_age <= 0:
        raise ValueError("空气龄必须为正")
    return nominal_age / (2 * average_age)


def ventilation_effectiveness(exhaust: float, supply: float, room: float) -> float:
    """排风、送风和室内污染物浓度 kg/m³ → 无量纲通风效率。"""
    if min(exhaust, supply, room) < 0 or room <= supply:
        raise ValueError("浓度无效")
    return (exhaust - supply) / (room - supply)


def measured_flow(velocity: float, area: float, coefficient: float = 1.0) -> float:
    """截面平均风速 m/s、有效面积 m²、流量系数 → 体积流量 m³/s。"""
    if velocity < 0 or area <= 0 or not 0 < coefficient <= 1:
        raise ValueError("流速、面积或系数无效")
    return velocity * area * coefficient
