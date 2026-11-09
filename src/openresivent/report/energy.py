"""第 4 章 M5 书稿片段，计算结果用 kWh 展示。"""


def render_energy(module: str, data: dict, result: dict) -> str:
    """模块、输入及 SI 年度结果 → 含参数来源的中文片段。"""
    rows = ["| 参数 | 符号 | 数值 | 单位 | 来源 |", "|---|---|---:|---|---|"]
    fields = [
        ("flow_m3_h", "设计新风量", "Q", "m³/h"),
        ("heating_temperature_c", "采暖室内温度", "t_{ih}", "℃"),
        ("cooling_temperature_c", "制冷室内温度", "t_{ic}", "℃"),
        ("heating_humidity_ratio", "采暖室内含湿量", "w_{ih}", "kg/kg"),
        ("cooling_humidity_ratio", "制冷室内含湿量", "w_{ic}", "kg/kg"),
        ("sensible_efficiency", "显热回收效率", "\\eta_s", "—"),
        ("enthalpy_efficiency", "焓回收效率", "\\eta_h", "—"),
        ("pm25_ug_m3", "室外颗粒物浓度", "C_p", "μg/m³"),
        ("cav_shutoff_pa", "CAV 风机关闭压力", "p_c", "Pa"),
        ("pid_shutoff_pa", "PID 风机关闭压力", "p_p", "Pa"),
        ("motor_efficiency", "风机总效率", "\\eta_f", "—"),
    ]
    for key, label, symbol, unit in fields:
        if key not in data:
            continue
        src = (
            "论文1第3页设计风量"
            if module == "energy_control" and key == "flow_m3_h"
            else "论文1第5页北京测试值；其他城市为假设，需作者确认"
            if key == "pm25_ug_m3"
            else "假设，需作者确认"
        )
        if module == "energy_control" and key in ("sensible_efficiency", "enthalpy_efficiency"):
            continue
        value = (
            f"{data[key] * 100:g}"
            if key in ("sensible_efficiency", "enthalpy_efficiency")
            else data[key]
        )
        if key in ("sensible_efficiency", "enthalpy_efficiency"):
            unit = "%"
        rows.append(f"| {label} | ${symbol}$ | {value} | {unit} | {src} |")
    rows += [
        "| 空气密度近似 | $\\rho$ | 1.2 | kg/m³ | 假设，需作者确认 |",
        "| 空气定压比热 | $c_p$ | 1006 | J/(kg·K) | ASHRAE Fundamentals 湿空气焓公式 |",
    ]
    body = [
        "",
        "**第一步：计算。**",
        "",
        "采暖采用显热法、制冷采用全热法；季节由论文1第13页表2确定，季外停机。气象为各城市机场或气象站的 2007–2021 TMYx，逐时计入，非研究原气象或现场实测。",
        "",
        "$$Q_h=\\rho c_pQ(T_i-T_o)(1-\\eta_s),\\quad Q_c=\\rho_d Q(h_o-h_i)(1-\\eta_h)$$",
        "",
    ]
    if module == "energy_control":
        body += [
            "使用论文1第5页式(1)滤网回归、第5页表1效率、第9页式(16)–(17)热泵 COP；风机曲线来自图4和图11读图，图示范围外线性外推，PID 超出能力不强制恒流。滤网每季起始更换，PM2.5 和设备工况不能作为四城市实测。",
            "",
            "| 城市 | CAV 新风负荷 kWh | PID 新风负荷 kWh | 新风负荷降幅 | 综合电耗节能率 | PID 不足风量小时 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    else:
        body += [
            "固定风量、不使用旁通；有热回收与无热回收对比。COP 取 1 为示例，仅以新风处理负荷和风机耗电量作框架比较，不代表住宅实际总耗电。",
            "",
            "| 城市 | 无回收新风负荷 kWh | 有回收新风负荷 kWh | 热回收量 kWh | 负荷降幅 | 风机电耗 kWh |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    names = {"harbin": "哈尔滨", "beijing": "北京", "shanghai": "上海", "guangzhou": "广州"}
    for city, x in result["cities"].items():
        base = x["baseline"]["annual"]
        alt = x["candidate"]["annual"]
        frac = x["load_reduction"]
        if module == "energy_control":
            body.append(
                f"| {names[city]} | {base['ventilation_j'] / 3.6e6:.1f} | {alt['ventilation_j'] / 3.6e6:.1f} | {frac * 100:.2f}% | {x['energy_saving'] * 100:.2f}% | {x['candidate']['target_unmet_hours']} |"
            )
        else:
            body.append(
                f"| {names[city]} | {base['ventilation_j'] / 3.6e6:.1f} | {alt['ventilation_j'] / 3.6e6:.1f} | {alt['recovered_j'] / 3.6e6:.1f} | {frac * 100:.2f}% | {alt['fan_j'] / 3.6e6:.1f} |"
            )
    sensitivity = result["cities"]["beijing"]["sensitivity"]
    sensitivity_text = "、".join(
        f"{k} 倍时 {v['load_reduction'] * 100:.2f}%" for k, v in sensitivity.items()
    )
    variable = "PM2.5 浓度" if module == "energy_control" else "显热及焓回收效率"
    body += [
        "",
        f"**敏感性说明：** 北京工况下，{variable}分别取基值的 {sensitivity_text}（数值为新风负荷降幅）。风机曲线为读图估计，外推及其余运行假设影响结果；不能将本结果当作论文定量复现或设计保证。",
        "",
        "本例不涉及条文判定。",
    ]
    return "\n".join(rows + body) + "\n"
