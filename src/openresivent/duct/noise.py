"""倍频程声功率传递和室内声压初算；不是现场验收测量。"""

import math

from scipy.optimize import brentq

BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 8000)


def sum_levels(levels):
    """非相干声级能量叠加；输入和输出为 dB。"""
    values = list(levels)
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError("声级必须为有限数")
    top = max(values)
    return top + 10 * math.log10(sum(10 ** ((x - top) / 10) for x in values))


def a_weight(frequency):
    """IEC 61672 A 计权响应；频率 Hz，返回修正 dB。"""
    if not math.isfinite(frequency) or frequency <= 0:
        raise ValueError("频率必须大于零")
    f2 = frequency**2
    response = (12194**2 * f2**2) / (
        (f2 + 20.6**2) * math.sqrt((f2 + 107.7**2) * (f2 + 737.9**2)) * (f2 + 12194**2)
    )
    return 20 * math.log10(response) + 2.0


def room_pressure(power_db, directivity, distance_m, room_constant_m2):
    """点声源室内关系：声功率级 dB、Q 无量纲、距离 m、房间常数 m² → 声压级 dB。"""
    if (
        not all(math.isfinite(x) for x in (power_db, directivity, distance_m, room_constant_m2))
        or min(directivity, distance_m, room_constant_m2) <= 0
    ):
        raise ValueError("声功率、指向因子、距离及房间常数无效")
    return power_db + 10 * math.log10(
        directivity / (4 * math.pi * distance_m**2) + 4 / room_constant_m2
    )


def room_pressure_thompson(
    power_db, directivity, distance_m, room_constant_m2, mean_free_path_m, absorption_per_m=0.0
):
    """Thompson 室内点声源公式，输入 dB、m、m²、m⁻¹，返回 dB。"""
    x = (power_db, directivity, distance_m, room_constant_m2, mean_free_path_m, absorption_per_m)
    if (
        not all(math.isfinite(v) for v in x)
        or min(directivity, distance_m, room_constant_m2, mean_free_path_m) <= 0
        or absorption_per_m < 0
    ):
        raise ValueError("声源或房间参数无效")
    return (
        power_db
        + 10
        * math.log10(
            directivity * math.exp(-absorption_per_m * distance_m) / (4 * math.pi * distance_m**2)
            + (mean_free_path_m / distance_m) * 4 / room_constant_m2
        )
        + 0.5
    )


def _spectrum(values, name):
    if not isinstance(values, (list, tuple)) or len(values) != len(BANDS):
        raise ValueError(f"{name}须为八个倍频程值")
    if any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
        for x in values
    ):
        raise ValueError(f"{name}须为有限数字")
    return list(map(float, values))


def calculate_noise(data: dict, flow_m3_s: float) -> dict:
    """输入声源和元件八频带 dB、流量 m³/s，返回逐频带与 A 声级。

    每段依次先衰减再叠加该段末尾再生声功率；末端反射仅衰减管内声。
    各声源频谱以统一正指数按流量标度，指数为工程假设且须校准。
    """
    ref = float(data["reference_flow_m3_s"])
    exp = float(data.get("flow_exponent", 5))
    if not all(math.isfinite(x) and x > 0 for x in (flow_m3_s, ref, exp)):
        raise ValueError("风量和指数必须为正")
    if "fan_power_db" in data:
        fan = _spectrum(data["fan_power_db"], "风机频谱")
    else:
        static_pressure = float(data["fan_pressure_pa"])
        specific = float(data["fan_specific_level_db"])
        if (
            not math.isfinite(static_pressure)
            or static_pressure <= 0
            or not math.isfinite(specific)
        ):
            raise ValueError("经验式风机压力或比声功率级无效")
        offsets = _spectrum(data["fan_octave_offsets_db"], "频谱修正")
        baseline = specific + 10 * math.log10(ref) + 20 * math.log10(static_pressure)
        fan = [baseline + x for x in offsets]
    reflection = _spectrum(data["terminal_reflection_db"], "末端反射")
    if any(x < 0 for x in reflection):
        raise ValueError("末端反射损失不得为负")
    stages = data["stages"]
    if not isinstance(stages, list):
        raise TypeError("风管元件须为列表")
    scale = 10 * exp * math.log10(flow_m3_s / ref)
    power = [x + scale for x in fan]
    history = []
    for stage in stages:
        if stage["kind"] not in ("straight", "bend", "silencer"):
            raise ValueError("未知风管元件")
        loss = _spectrum(stage["attenuation_db"], "元件衰减")
        if any(x < 0 for x in loss):
            raise ValueError("衰减不得为负")
        generated = stage.get("regenerated_db")
        gen = _spectrum(generated, "再生声") if generated is not None else None
        power = [
            sum_levels([p - l, g + scale]) if gen else p - l
            for p, l, g in zip(power, loss, gen or [0] * 8, strict=True)
        ]
        history.append({"kind": stage["kind"], "power_db": power.copy()})
    power = [x - loss for x, loss in zip(power, reflection, strict=True)]
    diffuser = data.get("diffuser_regenerated_db")
    if diffuser is not None:
        regenerated = _spectrum(diffuser, "风口再生声")
        power = [sum_levels([p, g + scale]) for p, g in zip(power, regenerated, strict=True)]
    pressure = [
        room_pressure(
            p,
            float(data["directivity"]),
            float(data["distance_m"]),
            float(data["room_constant_m2"]),
        )
        for p in power
    ]
    weighted = [p + a_weight(f) for p, f in zip(pressure, BANDS, strict=True)]
    return {
        "bands_hz": list(BANDS),
        "terminal_power_db": power,
        "room_pressure_db": pressure,
        "a_weighted_bands_db": weighted,
        "a_weighted_db": sum_levels(weighted),
        "stages": history,
        "flow_m3_s": flow_m3_s,
    }


def noise_case(data: dict) -> dict:
    """逐档和夜间目标反算；结果风量为 m³/s。"""
    reference = float(data["reference_flow_m3_s"])
    limit = float(data["target_db"])
    if not math.isfinite(limit):
        raise ValueError("目标声级无效")
    flows = data["flows_m3_s"]
    if not isinstance(flows, list) or not flows:
        raise ValueError("风量档位不能为空")
    results = [calculate_noise(data, float(q)) for q in flows]
    objective = lambda q: calculate_noise(data, q)["a_weighted_db"] - limit
    lo, hi = reference * 0.01, reference * 10
    if objective(lo) > 0 or objective(hi) < 0:
        raise ValueError("指定风量搜索范围无法包围声级限值")
    maximum = brentq(objective, lo, hi, xtol=1e-12)
    return {
        "settings": results,
        "maximum_flow_m3_s": maximum,
        "at_maximum_db": calculate_noise(data, maximum)["a_weighted_db"],
        "target_db": limit,
        "target_kind": data.get("target_kind", "示例目标"),
        "source_note": "风机频谱、衰减、再生声及流量指数须由设备与工程数据核实；未考虑结构传声及背景声。",
    }
