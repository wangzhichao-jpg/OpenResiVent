"""人体 CO₂ 生成率估算（Persily 和 de Jonge，Indoor Air 2017，DOI 10.1111/ina.12383）。"""


def co2_generation(
    weight_kg: float,
    sex: str,
    met: float,
    temperature_k: float,
    pressure_pa: float,
    rq: float = 0.85,
) -> float:
    """体重 kg、性别、活动代谢倍数、温度 K、压力 Pa、呼吸商 → CO₂ 体积流量 m³/s。

    Schofield 18–30 岁组基础代谢，输入体重 kg，输出 MJ/d；Persily/de Jonge
    公式中压力单位为 kPa、结果为 L/s。默认呼吸商依据 参考说明。
    """
    if weight_kg <= 0 or met <= 0 or temperature_k <= 0 or pressure_pa <= 0 or rq <= 0:
        raise ValueError("体重、代谢率、温度、压力及呼吸商必须为正")
    coefficients = {"male": (0.0630, 2.8957), "female": (0.0621, 2.0357)}
    if sex not in coefficients:
        raise ValueError("性别组必须为 male 或 female")
    a, b = coefficients[sex]
    bmr = a * weight_kg + b
    return rq * bmr * met * (temperature_k / (pressure_pa / 1000)) * 0.000179 / 1000
