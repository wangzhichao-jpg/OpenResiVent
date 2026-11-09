"""M7 等温住宅多区模板与联合工况；输入输出采用 SI。

门缝、过流口和容积是示例假设，不是产品性能或标准推荐值。额定机械
风量按理想定流量处理，不计算风机真实曲线或管道背压。
"""

from dataclasses import dataclass

from openresivent.dwelling.pressure import door_opening_force
from openresivent.network.elements import ConstantFlow, Orifice, airtightness_coefficient
from openresivent.network.solver import Link, Zone, solve


@dataclass(frozen=True)
class Dwelling:
    """卧室数、户内容积 m³、n50 s⁻¹，面积 m²；等分围护缝隙。"""

    bedrooms: int
    volume: float = 250.0
    n50: float = 1 / 3600
    kitchen_open: bool = False
    door_gap_area: float = 0.015
    transfer_area: float = 0.005
    discharge: float = 0.6
    exponent: float = 0.65
    rho: float = 1.2


def acceptance_scenarios() -> list[dict]:
    """列出应同时测压力、风量、门状态和开门力的工况。"""
    measures = [
        "各室相对室外压力",
        "门两侧压差及气流方向",
        "新风机送排风量",
        "补风量",
        "户门开启力",
        "门窗状态",
    ]
    return [
        {
            "name": "全部关闭的背景渗透",
            "hood": False,
            "ventilation": False,
            "bath_fan": False,
            "measure": measures.copy(),
        },
        {
            "name": "油烟机 + 新风",
            "hood": True,
            "ventilation": True,
            "bath_fan": False,
            "measure": measures.copy(),
        },
        {
            "name": "油烟机 + 新风 + 卫生间排风",
            "hood": True,
            "ventilation": True,
            "bath_fan": True,
            "measure": measures.copy(),
        },
    ]


def calculate(
    home: Dwelling,
    *,
    hood: float = 0,
    fresh_supply: float = 0,
    fresh_exhaust: float = 0,
    bath_exhaust: float = 0,
    opening_area: float = 0,
    mechanical_makeup: float = 0,
    interlock: str = "none",
    threshold_pa: float = 15,
    hood_room: str = "kitchen",
    supply_room: str | tuple[str, ...] = ("living", "bed1"),
    exhaust_room: str = "bath",
    bath_fan_room: str = "bath",
    opening_room: str = "kitchen",
    makeup_room: str = "kitchen",
    _network_only: bool = False,
) -> dict:
    """计算住宅网络；各风量 m³/s。联锁可为 none、stop_exhaust、increase_supply。

    increase_supply 增量等于油烟机额定风量；所需能力由设计者核实。
    各设备位置可配置；燃气具判据采用厨房负压；开敞厨房与起居室为同一区。
    气密性按假设等分到各室外墙缝，室内流道为孔口。
    """
    if home.bedrooms not in (2, 3, 4):
        raise ValueError("仅支持两至四卧室模板")
    if (
        min(home.volume, home.n50, home.door_gap_area, home.discharge, home.rho, threshold_pa) <= 0
        or home.transfer_area < 0
    ):
        raise ValueError("户型参数无效")
    if min(hood, fresh_supply, fresh_exhaust, bath_exhaust, opening_area, mechanical_makeup) < 0:
        raise ValueError("风量和面积不得为负")
    if interlock not in ("none", "stop_exhaust", "increase_supply"):
        raise ValueError("未知联锁模式")
    supply = fresh_supply + (hood if hood and interlock == "increase_supply" else 0)
    exhaust = 0 if hood and interlock == "stop_exhaust" else fresh_exhaust
    rooms = ["living", "bath"] + [f"bed{i}" for i in range(1, home.bedrooms + 1)]
    if not home.kitchen_open:
        rooms.append("kitchen")
    kitchen = "living" if home.kitchen_open else "kitchen"

    def resolve(room):
        room = kitchen if room == "kitchen" else room
        if room not in rooms:
            raise ValueError(f"设备房间不存在：{room}")
        return room

    hood_room, exhaust_room, bath_fan_room, opening_room, makeup_room = map(
        resolve, (hood_room, exhaust_room, bath_fan_room, opening_room, makeup_room)
    )
    supply_rooms = (
        (resolve(supply_room),)
        if isinstance(supply_room, str)
        else tuple(map(resolve, supply_room))
    )
    if not supply_rooms or len(set(supply_rooms)) != len(supply_rooms):
        raise ValueError("新风送风房间不能为空或重复")
    zones = {"outside": Zone(293.15, fixed=True, density_kg_m3=home.rho)}
    zones.update(
        {r: Zone(293.15, volume=home.volume / len(rooms), density_kg_m3=home.rho) for r in rooms}
    )
    links = []
    labels = []

    def add(name, link):
        labels.append(name)
        links.append(link)

    coefficient = airtightness_coefficient(home.n50, home.volume, home.exponent) / len(rooms)
    for r in rooms:
        add(f"envelope:{r}", Link("outside", r, coefficient, home.exponent))
    for r in rooms:
        if r != "living":
            area = home.door_gap_area + home.transfer_area
            add(
                f"door:{r}",
                Link("living", r, 1, 0.5, element=Orifice(home.discharge, area)),
            )
    if opening_area:
        add(
            "opening",
            Link(
                "outside",
                opening_room,
                1,
                0.5,
                element=Orifice(home.discharge, opening_area),
            ),
        )
    for name, start, end, q in [
        ("hood", hood_room, "outside", hood),
        ("fresh_exhaust", exhaust_room, "outside", exhaust),
        ("bath_fan", bath_fan_room, "outside", bath_exhaust),
        ("makeup", "outside", makeup_room, mechanical_makeup),
    ]:
        if q:
            add(name, Link(start, end, 1, 1, element=ConstantFlow(q)))
    if supply:
        for room in supply_rooms:
            label = "fresh_supply" if len(supply_rooms) == 1 else f"fresh_supply:{room}"
            add(
                label, Link("outside", room, 1, 1, element=ConstantFlow(supply / len(supply_rooms)))
            )
    if _network_only:
        return {"zones": zones, "links": links, "labels": labels}
    result = solve(zones, links, tolerance=1e-11)
    flows = {
        name: {"start": link.start, "end": link.end, **flow}
        for name, link, flow in zip(labels, links, result["flows"], strict=True)
    }
    pressures = result["pressures"]
    return {
        "pressures_pa": pressures,
        "device_rooms": {
            "hood": hood_room,
            "fresh_supply": supply_rooms[0] if len(supply_rooms) == 1 else list(supply_rooms),
            "fresh_exhaust": exhaust_room,
            "bath_fan": bath_fan_room,
            "opening": opening_room,
            "makeup": makeup_room,
        },
        "flows": flows,
        "doors": {
            r: {
                "delta_p_pa": pressures["living"] - pressures[r],
                "direction": "living→" + r
                if flows["door:" + r]["volume_flow"] >= 0
                else r + "→living",
            }
            for r in rooms
            if r != "living"
        },
        "fresh_supply_m3_s": supply,
        "fresh_exhaust_m3_s": exhaust,
        "normal_exhaust_supply_ratio": fresh_exhaust / fresh_supply if fresh_supply else None,
        "normal_ratio_80_90": (0.8 <= fresh_exhaust / fresh_supply <= 0.9)
        if fresh_supply
        else None,
        "opening_m3_s": flows.get("opening", {}).get("volume_flow", 0.0),
        "entrance_opening_force_n": door_opening_force(0.9, 2.1, 0.06, pressures["living"]),
        "gas_zone": kitchen,
        "negative_pressure_warning": pressures[kitchen] < -threshold_pa,
        "makeup_location_warning": "补风口宜设在厨房本地"
        if hood
        and (
            (opening_area and opening_room != hood_room)
            or (mechanical_makeup and makeup_room != hood_room)
        )
        else None,
        "threshold_pa": threshold_pa,
        "mass_residual_kg_s": result["mass_residual"],
        "acceptance_scenarios": acceptance_scenarios(),
    }
