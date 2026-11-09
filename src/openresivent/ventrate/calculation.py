"""住宅新风量，核心均为 SI；依据 JGJ/T 440-2018 4.2.1–4.2.3。"""

from dataclasses import dataclass

from openresivent.ventrate.pollutant import steady_flow


@dataclass(frozen=True)
class Room:
    """房间面积 m²、净高 m、人数及人体 CO₂ 排放量 m³/s/人。"""

    area: float
    height: float
    occupants: float
    co2_per_person: float = 18e-3 / 3600
    hcho_generation: float = 0.0


def air_changes_rate(area_per_person: float) -> float:
    """人均居住面积 m²/人 → 最小换气次数 s⁻¹；JGJ/T 440-2018 表 4.2.1。"""
    if area_per_person <= 0:
        raise ValueError("人均面积必须为正")
    return (
        0.7
        if area_per_person <= 10
        else 0.6
        if area_per_person <= 20
        else 0.5
        if area_per_person <= 50
        else 0.45
    ) / 3600


def co2_flow(generation: float, outdoor: float, limit: float) -> float:
    """CO₂ 排放量 m³/s、室外及限值体积分数 → 新风量 m³/s；440 式 4.2.2。"""
    if generation < 0 or outdoor < 0 or limit <= outdoor or limit > 1:
        raise ValueError("排放量或浓度无效")
    return generation / (limit - outdoor)


def ashrae_flow(area: float, bedrooms: int) -> float:
    """面积 m²、卧室数 → 新风量 m³/s；ASHRAE 62.2-2025，见方案 5 M1。"""
    if area <= 0 or bedrooms < 0:
        raise ValueError("面积和卧室数无效")
    return (0.15 * area + 3.5 * (bedrooms + 1)) / 1000


def en_co2_flow(generation: float, category: str) -> float:
    """CO₂ 排放量 m³/s、EN 室内空气类别 I/II/III → 风量 m³/s。

    超室外浓度按示例条件 T6，分别为 550、800、1350 ppm。
    """
    excess = {"I": 550e-6, "II": 800e-6, "III": 1350e-6}
    if category not in excess or generation < 0:
        raise ValueError("类别或排放量无效")
    return generation / excess[category]


def calculate_dwelling(
    area: float,
    height: float,
    occupants: float,
    bedrooms: list[Room],
    living: Room,
    *,
    include_people: bool = True,
    outdoor: float = 400e-6,
    limit: float = 1000e-6,
    allowance: float = 0.05,
    hcho_outdoor: float = 0.0,
    hcho_limit: float = 0.08e-6,
    hcho_whole_generation: float = 0.0,
) -> dict:
    """全户居住面积 m²、净高 m、人数、房间；返回各项风量 m³/s。

    440 4.2.3 房间法为卧室与起居室之和；18883 人员法按启用状态参与。
    风量附加率依据 440 5.2.1，居室人数重复计入的理由见 参考说明。
    """
    if area <= 0 or height <= 0 or occupants <= 0 or not bedrooms:
        raise ValueError("面积、净高、人数及卧室不能为空或非正")
    if not 0.05 <= allowance <= 0.10:
        raise ValueError("风量附加率应为 5% 至 10%")
    if hcho_whole_generation < 0 or hcho_outdoor < 0 or hcho_limit <= hcho_outdoor:
        raise ValueError("甲醛源强或浓度无效")
    if any(
        r.area <= 0
        or r.height <= 0
        or r.occupants < 0
        or r.co2_per_person < 0
        or r.hcho_generation < 0
        for r in [*bedrooms, living]
    ):
        raise ValueError("房间参数无效")
    n = air_changes_rate(area / occupants)
    per_person = 30 / 3600
    rooms = []
    sum_440 = 0.0
    sum_all = 0.0
    for room in bedrooms:
        a = room.area * room.height * n
        c = co2_flow(room.occupants * room.co2_per_person, outdoor, limit)
        b = room.occupants * per_person
        base = max(a, c)
        d = (
            steady_flow(room.hcho_generation, hcho_outdoor, hcho_limit)
            if room.hcho_generation
            else 0.0
        )
        selected = max(base, b if include_people else 0, d)
        sum_440 += base
        sum_all += selected
        rooms.append(
            {"A": a, "B": b if include_people else None, "C": c, "D": d, "selected": selected}
        )
    a_living = living.area * living.height * n
    b_living = occupants * per_person
    sum_440 += a_living
    d_living = (
        steady_flow(living.hcho_generation, hcho_outdoor, hcho_limit)
        if living.hcho_generation
        else 0.0
    )
    sum_all += max(a_living, b_living if include_people else 0, d_living)
    minimum = area * height * n
    whole_b = occupants * per_person
    only_440 = max(minimum, sum_440)
    whole_d = (
        steady_flow(hcho_whole_generation, hcho_outdoor, hcho_limit)
        if hcho_whole_generation
        else 0.0
    )
    selected = max(minimum, sum_all, whole_b if include_people else 0, whole_d)
    return {
        "rate_per_s": n,
        "bedrooms": rooms,
        "living": {"A": a_living, "B": b_living if include_people else None, "D": d_living},
        "whole_A": minimum,
        "whole_B": whole_b if include_people else None,
        "whole_D": whole_d,
        "room_total": sum_all,
        "only_440": only_440,
        "design": selected,
        "fan": selected * (1 + allowance),
        "sources": {
            "A": "JGJ/T 440-2018 4.2.1",
            "B": "GB/T 18883-2022",
            "C": "JGJ/T 440-2018 4.2.2",
            "D": "书稿式2-3与GB/T 18883-2022表1",
            "design": "JGJ/T 440-2018 4.2.3",
            "fan": "JGJ/T 440-2018 5.2.1",
        },
    }
