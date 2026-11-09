"""第4章附加算例书稿演算。"""

META = {
    "design_m3_h": ("设计风量", "Q_d", "m³/h"),
    "dust_g": ("积尘量序列", "m", "g"),
    "volume_m3": ("房间空气体积", "V", "m³"),
    "base_ach": ("闭窗换气次数", "n_0", "h⁻¹"),
    "mechanical_ach": ("机械通风换气次数", "n_1", "h⁻¹"),
    "indoor_t_k": ("室内温度", "T_i", "K"),
    "indoor_humidity_ratio": ("室内含湿量", "w_i", "kg/kg"),
    "dry_density": ("干空气密度", "rho", "kg/m³"),
    "enthalpy_efficiency": ("假设焓交换效率", "eta_h", "—"),
    "area_m2": ("卧室面积", "A", "m²"),
    "height_m": ("净高", "H", "m"),
    "occupants": ("卧室人数", "N", "人"),
    "whole_area_per_person_m2": ("全户人均居住面积", "a", "m²/人"),
    "co2_l_h_person": ("人均二氧化碳排放量", "G", "L/(h·人)"),
    "outdoor_ppm": ("室外浓度", "C_o", "ppm"),
    "limit_ppm": ("室内设计浓度", "C_i", "ppm"),
    "rated_m3_h": ("单台额定风量", "Q_n", "m³/h"),
    "devices": ("设备台数", "N_d", "台"),
    "effectiveness": ("有效换气率", "eta", "—"),
    "speed_m_s": ("出口速度", "v", "m/s"),
    "layout": ("风口布局", "L", "—"),
    "spacing_m": ("风口间距", "s", "m"),
    "opposed": ("风口相对", "O", "—"),
}


def render(module: str, d: dict, r: dict) -> str:
    """输入表、演算与局限；结果单位为工程展示单位。"""
    names = {"horizontal": "水平", "vertical": "垂直", "False": "否", "True": "是"}
    lines = ["| 参数 | 符号 | 数值 | 单位 | 来源 |", "|---|---|---:|---|---|"]
    for key, value in d.items():
        label, symbol, unit = META[key]
        lines.append(
            f"| {label} | ${symbol}$ | {names.get(str(value), value)} | {unit} | 假设，需作者确认 |"
        )
    lines += ["", "**第一步：计算。**"]
    if module == "p303_vav":
        lines += [
            "以论文图11风机压力与功率曲线读图为基准，依据相似定律对同一风机调速，假设额定点实测功率为96 W；理想调速不包含变频器及电机低速效率损失。",
            "| 积尘 g | PID 风量 m³/h | VAV 风量 m³/h | PID 功率 W | VAV 功率 W | 功率降幅 |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for x in r["rows"]:
            lines.append(
                f"| {x['dust_kg'] * 1000:g} | {x['pid']['flow_m3_s'] * 3600:.2f} | {x['vav']['flow_m3_s'] * 3600:.2f} | {x['pid']['fan_power_w']:.2f} | {x['vav']['fan_power_w']:.2f} | {x['saving'] * 100:.2f}% |"
            )
        lines += [
            "| 城市 | PID全年综合电耗 kWh | VAV全年综合电耗 kWh | 综合节能率 |",
            "|---|---:|---:|---:|",
        ]
        names_city = {
            "harbin": "哈尔滨",
            "beijing": "北京",
            "shanghai": "上海",
            "guangzhou": "广州",
        }
        for city, x in r["cities"].items():
            p = x["pid"]["annual"]
            v = x["vav"]["annual"]
            lines.append(
                f"| {names_city[city]} | {(p['hvac_electric_j'] + p['fan_j']) / 3.6e6:.2f} | {(v['hvac_electric_j'] + v['fan_j']) / 3.6e6:.2f} | {x['energy_saving'] * 100:.2f}% |"
            )
        lines += [
            "全年综合电耗为新风处理对应的空调电耗与风机电耗之和，不含建筑围护等负荷；书稿进一步节能12%～16%口径与模型边界不同。",
            "**敏感性说明：** 上表列出不同积尘量的影响，实际性能需设备测试。",
            "本例不涉及条文判定。",
        ]
    elif module == "p303_guangzhou":
        lines += [
            r"$$Q=\dot m(h_o-h_i),\quad E=\sum\max(0,Q)\Delta t$$",
            "书稿4.6.2引用的广州连续机械通风耗冷量增加约16%为 DeST-h 整栋建筑模拟的文献值，不由本算例计算。",
            f"全年室外焓低于室内 {r['free_cooling_hours']} h；在固定室内状态、连续机械风量及理想利用下，设置焓交换器不旁通的自然冷却潜力为 {r['free_cooling_without_bypass_j'] / 3.6e6:.2f} kWh，焓差旁通后为 {r['free_cooling_with_bypass_j'] / 3.6e6:.2f} kWh，增加 {r['bypass_extra_free_cooling_j'] / 3.6e6:.2f} kWh。",
            f"全年新风正冷负荷不旁通与焓差旁通分别为 {r['cooling_without_bypass_j'] / 3.6e6:.2f}、{r['cooling_with_bypass_j'] / 3.6e6:.2f} kWh；本计算正负负荷分开，不能把自然冷却潜力直接算作已实现节能。",
            "**敏感性说明：** 旁通可用冷量随室内状态及焓交换效率变化；本例未考虑建筑冷负荷上限、空调启停和蓄冷，须另行核算。",
            "本例不涉及条文判定。",
        ]
    else:
        lines += [
            f"JGJ/T 440-2018 第4.2.2条计算：换气次数法 {r['ach_flow_m3_s'] * 3600:.2f} m³/h、二氧化碳法 {r['co2_flow_m3_s'] * 3600:.2f} m³/h，取较大值 {r['demand_m3_s'] * 3600:.2f} m³/h。"
        ]
        for x in r["results"]:
            lines.append(
                f"设备额定风量乘有效换气率 {x['effectiveness'] * 100:.0f}% 后为 {x['effective_flow_m3_s'] * 3600:.2f} m³/h，{'满足' if x['satisfied'] else '不满足'}需求。"
            )
        lines += [
            f"JGJ/T 440-2018 第4.3.7条第1款：{'满足' if r['one_unit_recommended'] else '不满足'}一间房宜一套设备的建议；第4.3.7条第2款：{'存在' if r['outlet_check']['short_circuit_warning'] else '未发现几何层面的'}送排风短路风险，须结合实际气流复核。",
            "有效换气率0.7、0.8为假设而非具体设备检测值；应按产品试验数据及其工况核实。",
            "**敏感性说明：** 有效换气率变化已逐项列示，不能将额定风量直接视为有效新风量。",
        ]
    return "\n".join(lines) + "\n"
