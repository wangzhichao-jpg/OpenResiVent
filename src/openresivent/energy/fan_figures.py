"""吕伟华等 2023 图 4、11 风机曲线的像素读图估计，不是原始数据。

绘图坐标、原始读数、误差及图中遮挡见 docs/verification/M5_风机读图.md。
流量表以 m³/h 标注，接口始终以 m³/s 输入；端点外为明确标注的
线性延长，仅用于求交，不代表所选风机超出图示范围的实测性能。
"""

from scipy.optimize import brentq

# 从论文图按坐标轴和图中彩色标记中心换算，P Pa，N W。
Q_H = (140, 175, 210, 245, 280, 315, 350)
CAV_P = (200.5, 195.8, 183.0, 162.8, 153.0, 139.3, 118.9)
CAV_N = (54.5, 61.2, 69.2, 76.7, 84.4, 93.5, 103.5)
PID_P = (300.4, 291.6, 282.7, 263.3, 249.3, 239.4, 219.2)
PID_N = (82.7, 93.3, 105.5, 116.5, 128.9, 142.5, 158.1)


def interpolate(flow: float, values: tuple[float, ...]) -> float:
    """风量 m³/s、数据点 → 线性插值；端点外线性外推。"""
    if flow < 0 or len(values) != len(Q_H):
        raise ValueError("风量或读图曲线无效")
    x = flow * 3600
    i = next((i for i in range(len(Q_H) - 1) if x <= Q_H[i + 1]), len(Q_H) - 2)
    return values[i] + (values[i + 1] - values[i]) * (x - Q_H[i]) / (Q_H[i + 1] - Q_H[i])


def pressure(flow: float, mode: str) -> float:
    """流量 m³/s、cav/pid → 风机压力 Pa，图外计算为线性外推。"""
    if mode not in ("cav", "pid"):
        raise ValueError("未知风机")
    return interpolate(flow, CAV_P if mode == "cav" else PID_P)


def electrical_power(flow: float, mode: str, *, on_design: bool = False) -> float:
    """风量 m³/s → 电功率 W；CAV 用论文第 8 页式(11)，PID 设计点用第 7 页。"""
    if flow < 0 or mode not in ("cav", "pid"):
        raise ValueError("风机功率参数无效")
    if mode == "cav":
        # 原文式(11)单位标作 kW，但图4右轴是 W；本式数值按图及物理量纲为 W。
        return 0.2316 * (flow * 3600) + 20.679
    return 96.0 if on_design else interpolate(flow, PID_N)


def solve_flow(mode: str, resistance, setpoint: float, pid_min_pressure: float) -> dict:
    """阻力函数 Pa(Q m³/s) 与设定风量 → 读图曲线工作点及功率。"""
    if setpoint <= 0 or pid_min_pressure < 0 or mode not in ("cav", "pid"):
        raise ValueError("设定风量或控制模式无效")
    if mode == "pid" and pressure(setpoint, mode) >= resistance(setpoint) + pid_min_pressure:
        q = setpoint
        p = pressure(q, mode)
        valve = p - resistance(q)
        met = True
    else:
        valve = pid_min_pressure if mode == "pid" else 0.0
        upper = 350 / 3600
        while pressure(upper, mode) > resistance(upper) + valve and upper < 5:
            upper *= 1.5
        if pressure(0, mode) <= resistance(0) + valve:
            raise ValueError("读图曲线的零流量外推不足以克服系统压力")
        q = brentq(lambda x: pressure(x, mode) - resistance(x) - valve, 0, upper, xtol=1e-13)
        p = pressure(q, mode)
        met = q >= setpoint * (1 - 1e-8)
    return {
        "flow_m3_s": q,
        "pressure_pa": p,
        "valve_pressure_pa": valve,
        "fan_power_w": electrical_power(q, mode, on_design=(mode == "pid" and met)),
        "target_met": met,
        "curve_extrapolated": not Q_H[0] <= q * 3600 <= Q_H[-1],
    }
