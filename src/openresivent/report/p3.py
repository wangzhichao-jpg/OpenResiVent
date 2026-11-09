"""M8、M9 书稿片段。"""

META = {
    "cd": ("流量系数", "C_d", "—"),
    "single_area_m2": ("单开口面积", "A", "m²"),
    "opening_height_m": ("单开口高度", "h_o", "m"),
    "a1_m2": ("下开口面积", "A_1", "m²"),
    "a2_m2": ("上开口面积", "A_2", "m²"),
    "height_m": ("高差", "h", "m"),
    "delta_t_k": ("温差", "\\Delta T", "K"),
    "mean_t_k": ("平均温度", "\\bar T", "K"),
    "inside_t_k": ("室内温度", "T_i", "K"),
    "outside_t_k": ("室外温度", "T_o", "K"),
    "wind_m_s": ("风速", "v_w", "m/s"),
    "cp1": ("迎风风压系数", "C_{p1}", "—"),
    "cp2": ("背风风压系数", "C_{p2}", "—"),
    "speed_m_s": ("出口速度", "v_0", "m/s"),
    "diameter_m": ("出口直径", "d_0", "m"),
    "turbulence": ("射流紊流系数", "a", "—"),
    "distance_m": ("射流距离", "x", "m"),
    "temperature_difference_k": ("初始温差", "\\Delta T_0", "K"),
    "target_m_s": ("末端目标速度", "v_t", "m/s"),
    "layout": ("布置方式", "L", "—"),
    "spacing_m": ("送排风口间距", "s", "m"),
    "opposed": ("送排风口相对", "O", "—"),
    "turbine_m3_s": ("涡轮风帽风量", "Q_t", "m³/s"),
    "natural_m3_s": ("同条件自然开口风量", "Q_n", "m³/s"),
    "static_m3_s": ("静态风帽风量", "Q_s", "m³/s"),
    "pressure_pa": ("入口压力", "p", "Pa"),
    "paper11_pressure_pa": ("论文11入口压力", "p_{11}", "Pa"),
    "angle_deg": ("风向上倾角", "\\theta", "°"),
    "source": ("污染源类型", "S", "—"),
    "horizontal_m": ("水平距离", "L_h", "m"),
    "vertical_m": ("垂直距离", "L_v", "m"),
    "intake_below": ("新风口在下方", "B", "—"),
    "same_direction": ("同向设置", "D", "—"),
    "ground_m": ("进风口下缘离地", "H", "m"),
    "green": ("绿化地带", "G", "—"),
}


def render(module: str, d: dict, r: dict) -> str:
    """生成输入表、演算与说明；假设不冒称实测。"""
    lines = ["| 参数 | 符号 | 数值 | 单位 | 来源 |", "|---|---|---:|---|---|"]
    names = {
        "horizontal": "水平",
        "vertical": "垂直",
        "water_heater": "燃气热水器排烟口",
        "True": "是",
        "False": "否",
    }
    for key, value in d.items():
        title, symbol, unit = META[key]
        lines.append(
            f"| {title} | ${symbol}$ | {names.get(str(value), value)} | {unit} | 假设，需作者确认 |"
        )
    lines += ["", "**第一步：计算。**", ""]
    if module == "p3_natural":
        n = r["thermal_network"]
        combined = r["coupled_network"]
        lines += [
            "CIBSE 单开口和双开口热压近似：",
            r"$$Q_1=\frac{C_dA}{3}\sqrt{\frac{gh\Delta T}{\bar T}},\quad A^*=\left(A_1^{-2}+A_2^{-2}\right)^{-1/2},\quad Q_2=C_dA^*\sqrt{\frac{2gh\Delta T}{\bar T}}$$",
            f"单开口 {r['single_m3_s']:.6f} m³/s；双开口等效面积 {r['double']['equivalent_area_m2']:.6f} m²、流量 {r['double']['flow_m3_s']:.6f} m³/s。",
            f"书稿对照式 (2-7)、(2-8) 带根号，计算分别为 {r['book_single']:.6f}、{r['book_double']:.6f} m³/s；双孔采用串联等效面积。经验系数含单位，结果与 CIBSE 式因系数及参考温度不同而有差异。",
            f"M2 纯热压入口/出口分别 {n['flows'][0]['volume_flow']:.6f}/{n['flows'][1]['volume_flow']:.6f} m³/s；含风压联合时分别 {combined['flows'][0]['volume_flow']:.6f}/{combined['flows'][1]['volume_flow']:.6f} m³/s。因两侧密度不同，体积流量不同而质量守恒；孔口质量流量按上游空气密度修正。",
            "**敏感性说明：** 流量系数取0.8、1.2倍时单开口风量为 "
            + "、".join(f"{v:.4f}" for v in r["sensitivity"].values())
            + " m³/s。",
            "本例不涉及条文判定。",
        ]
    elif module == "p3_jet":
        x = r["jet"]
        c = r["check"]
        lines += [
            r"$$v_x=v_0\frac{0.48}{ax/d_0+0.147},\quad \Delta T_x=\Delta T_0\frac{0.35}{ax/d_0+0.147}$$",
            f"轴心速度 {x['velocity_m_s']:.3f} m/s，轴心温差 {x['temperature_difference_k']:.3f} K，目标射程 {x['throw_m']:.3f} m。",
            f"JGJ/T 440-2018 第 4.4.4 条：风口速度 {d['speed_m_s']} m/s，{'满足' if c['speed_recommended'] else '不满足'}不宜大于3 m/s的要求；送排风口间距 {d['spacing_m']} m，{'满足' if c['spacing_passed'] else '不满足'}间距要求；{'存在' if c['short_circuit_warning'] else '未发现几何层面的'}短路风险，按第4.3.7条结合实际气流复核。",
            "**敏感性说明：** 紊流系数取0.8、1.2倍时射程为 "
            + "、".join(f"{v:.3f}" for v in r["sensitivity"].values())
            + " m；实际受限射流需现场复核。",
        ]
    elif module == "p3_stack":
        f = r["network"]["flows"]
        lines += [
            f"M2 网络求得入口 {f[0]['volume_flow']:.4f}、出口 {f[1]['volume_flow']:.4f} m³/s；不同温度下体积流量不相等。",
            "**敏感性说明：** 入口面积取0.8、1.2倍时入口流量为 "
            + "、".join(f"{v:.4f}" for v in r["sensitivity"].values())
            + " m³/s。",
            "本例不涉及条文判定。",
        ]
    elif module == "p3_cap":
        x = r["metrics"]
        s = r["suitability"]
        lines += [
            f"三种假设风量仅作指标定义示例，并非下列正压读图工况：风帽/自然开口比 $\\gamma={x['gamma_natural']:.3f}$；相对静态风帽风量增率 $\\varphi={x['phi_static'] * 100:.2f}\\%$。论文13的 $\\gamma$ 为风帽/静态风帽，即 {x['paper13_gamma']:.3f}，与自然开口参照不同。",
            f"论文13图7a Φ200 风帽在入口压力 {d['pressure_pa']} Pa 时零增益临界风速约 {s['threshold_m_s']:.1f} m/s；给定 {d['wind_m_s']} m/s 时{'优于' if s['turbine_better_than_static'] else '不优于'}静态风帽（仅特定装置及该工况）。论文11图19读图 {r['paper11_flow_m3_s'] * 1000:.0f} L/s，论文12图11的敞口排量比约 {r['paper12_cd']:.2f}。",
            f"论文13图6 Φ280 拟合在相同入口压力与风速下计算：涡轮风帽 {r['paper13_phi280']['turbine_m3_s']:.4f} m³/s，静态风帽 {r['paper13_phi280']['static_m3_s']:.4f} m³/s，风量增率 {r['paper13_phi280']['phi'] * 100:.1f}%（假设空气密度1.2 kg/m³、静态阻力系数1.5；非 Φ200 图7a，同样不能跨设备混同）。",
            "**敏感性说明：** 正压6、10、15 Pa时临界风速分别为 "
            + "、".join(f"{v['threshold_m_s']:.1f}" for v in r["sensitivity"].values())
            + " m/s；读图误差及局限见相关研究。",
            "本例不涉及条文判定。",
        ]
    else:
        x = r["check"]
        lines += [
            f"JGJ/T 440-2018 第4.4.1条：该污染源与新风口给定布置{'满足' if x['pollution_passed'] else '不满足'}距离要求；分户式进排口{'满足' if x['decentral_passed'] else '不满足'}位置要求。",
            f"GB 50736-2012 第6.3.1条：进风口下缘离地 {d['ground_m']} m，{'满足' if x['ground_recommended'] else '不满足'}不宜低于规定高度的要求。",
            "**敏感性说明：** 水平距离1.2、1.5、1.8 m时污染源距离要求分别为 "
            + "、".join("满足" if a else "不满足" for a in r["sensitivity"].values())
            + "；其他污染源和复杂建筑构型应另行核查。",
        ]
    return "\n".join(lines) + "\n"
