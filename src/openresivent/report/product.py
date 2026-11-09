"""产品检测算例的书稿片段。"""

META = {
    "supply_mass_kg_s": ("送风干空气质量流量", "m_s", "kg/s"),
    "exhaust_mass_kg_s": ("排风干空气质量流量", "m_e", "kg/s"),
    "outdoor_t_k": ("室外温度", "T_o", "K"),
    "exhaust_t_k": ("排风入口温度", "T_e", "K"),
    "supply_t_k": ("送风出口温度", "T_s", "K"),
    "outdoor_w": ("室外含湿量", "w_o", "kg/kg"),
    "exhaust_w": ("排风含湿量", "w_e", "kg/kg"),
    "supply_w": ("送风含湿量", "w_s", "kg/kg"),
    "fan_flow_m3_h": ("原风机风量", "Q_0", "m³/h"),
    "fan_pressure_pa": ("原风机压力", "p_0", "Pa"),
    "fan_power_w": ("原风机功率", "P_0", "W"),
    "speed_ratio": ("转速比", "r", "—"),
    "test_flow_m3_h": ("检测风量", "Q", "m³/h"),
    "test_power_w": ("检测功率", "W", "W"),
    "pm25_efficiency": ("颗粒物一次通过效率", "E", "%"),
    "kind": ("气流形式", "F", "—"),
}


def input_rows(d):
    rows = []
    for k, v in d.items():
        name, symbol, unit = META[k]
        value = (
            v * 100
            if k == "pm25_efficiency"
            else {"single": "单向流", "dual": "双向流"}.get(v, v)
            if isinstance(v, str)
            else v
        )
        rows.append(f"| {name} | ${symbol}$ | {value} | {unit} | 假设，需作者确认 |")
    return rows


def render(d: dict, r: dict) -> str:
    """输入与检测结果转为 Markdown。"""
    e = r["exchange"]
    f = r["fan"]
    s = r["specific"]
    p = r["purification"]
    return (
        "\n".join(
            [
                "| 参数 | 符号 | 数值 | 单位 | 来源 |",
                "|---|---|---:|---|---|",
                *input_rows(d),
                "",
                "**第一步：计算。**",
                r"$$\varepsilon_s=\frac{\dot m_s(T_s-T_o)}{\dot m_{min}(T_e-T_o)},\quad \varepsilon_l=\frac{\dot m_s(w_s-w_o)}{\dot m_{min}(w_e-w_o)},\quad \varepsilon_t=\frac{\dot m_s(h_s-h_o)}{\dot m_{min}(h_e-h_o)}$$",
                f"显热效率 {e['sensible'] * 100:.2f}%，潜热效率 {e['latent'] * 100:.2f}%，全热效率 {e['total'] * 100:.2f}%。质量流量取干空气，最小质量流量归一化。",
                f"风机相似定律换算后风量 {f['flow_m3_s'] * 3600:.2f} m³/h、压力 {f['pressure_pa']:.2f} Pa、功率 {f['power_w']:.3f} W；同密度、相似工况近似。",
                f"单位风量耗功率 {s['w_per_m3_h']:.2f} W/(m³/h)，SFP {s['sfp_w_per_m3_s']:.1f} W/(m³/s)。",
                f"JGJ/T 440-2018 第5.2.6条：净化能效 {p['value_m3_wh']:.2f} m³/(W·h)，结果为{p['grade']}（节能级界限 {p['saving_limit']:.2f}、合格级下限 {p['qualified_limit']:.2f}）。",
                f"**敏感性说明：** 其他条件不变，功率取原来的0.8、1.2倍时净化能效分别为 {p['value_m3_wh'] / 0.8:.2f}、{p['value_m3_wh'] / 1.2:.2f} m³/(W·h)；本例为假设输入，须以检测数据复核。",
            ]
        )
        + "\n"
    )
