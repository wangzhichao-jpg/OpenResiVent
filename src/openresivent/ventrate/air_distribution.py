"""射流近似及现行条文的参数化校核。"""


def jet(
    velocity: float,
    diameter: float,
    turbulence: float,
    distance: float,
    temperature_difference: float,
    target_velocity: float,
) -> dict:
    """出口速度 m/s、直径/距离 m、紊流系数、温差 K、目标速度 m/s → 轴心速度和射程。"""
    if min(velocity, diameter, turbulence, target_velocity) <= 0 or distance < 0:
        raise ValueError("射流参数无效")
    factor = turbulence * distance / diameter + 0.147
    return {
        "velocity_m_s": velocity * 0.48 / factor,
        "temperature_difference_k": temperature_difference * 0.35 / factor,
        "jet_diameter_m": diameter * 6.8 * factor,
        "throw_m": diameter / turbulence * (0.48 * velocity / target_velocity - 0.147),
    }


def indoor_outlets(speed: float, arrangement: str, distance: float, opposed: bool = False) -> dict:
    """风口速度 m/s、相对位置、间距 m、是否相对布置 → 宜项与不应项。"""
    if speed < 0 or distance < 0 or arrangement not in ("horizontal", "vertical"):
        raise ValueError("风口参数无效")
    return {
        "speed_recommended": speed <= 3,
        "not_opposed": not opposed,
        "spacing_passed": distance >= 1,
        "short_circuit_warning": opposed or distance < 1,
        "strength": {"speed": "宜", "arrangement": "应", "spacing": "应"},
    }


def outdoor_intake(
    source: str,
    horizontal: float,
    vertical: float,
    *,
    intake_below: bool,
    layout: str,
    same_direction: bool,
    ground_clearance: float,
    green: bool = False,
    matrix: dict | None = None,
    in_cavity: bool = False,
) -> dict:
    """源类型、水平/垂直距离 m、相对方位与离地高度 m → 当前条文及可选矩阵。"""
    sources = ("water_heater", "kitchen", "bathroom", "ac_outdoor", "garage", "own_exhaust")
    if (
        source not in sources
        or min(horizontal, vertical, ground_clearance) < 0
        or layout not in ("horizontal", "vertical")
    ):
        raise ValueError("新风口几何参数无效")
    pollution_passed = (
        None
        if source == "own_exhaust"
        else (horizontal >= 1.5 if layout == "horizontal" else vertical >= 1.5 and intake_below)
    )
    decentral = (
        (not same_direction or horizontal >= 1)
        if layout == "horizontal"
        else (intake_below and vertical >= 1)
    )
    ground = ground_clearance >= (1 if green else 2)
    matrix_result = None
    if matrix is not None:
        if source not in matrix:
            raise ValueError("矩阵缺少污染源")
        spec = matrix[source]
        if set(spec) != {"horizontal_m", "vertical_m"} or min(spec.values()) < 0:
            raise ValueError("矩阵字段无效")
        matrix_result = {
            "passed": horizontal >= spec["horizontal_m"] and vertical >= spec["vertical_m"],
            "source": "用户提供研究矩阵，非现行条文",
        }
    return {
        "pollution_passed": pollution_passed,
        "decentral_passed": decentral,
        "ground_recommended": ground,
        "ground_strength": "宜",
        "decentral_strength": "应" if layout == "horizontal" else "宜",
        "matrix_result": matrix_result,
        "cavity_warning": in_cavity,
    }
