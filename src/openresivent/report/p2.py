"""P2 算例书稿片段；不添加章节标题，示例与假设明确标注。"""


def render_p2(module: str, data: dict, result: dict) -> str:
    """构造参数表和计算步骤；结果按工程位数显示，JSON 保持精度。"""
    rows = ["| 参数 | 符号 | 数值 | 单位 | 来源 |", "|---|---|---:|---|---|"]

    def row(label, symbol, value, unit, source="假设，需作者确认"):
        rows.append(f"| {label} | ${symbol}$ | {value} | {unit} | {source} |")

    body = ["", "**第一步：计算。**", ""]
    if module == "p2_fan":
        for key, label, symbol, unit in [
            ("free_flow_m3_h", "自由风量", "Q_0", "m³/h"),
            ("shutoff_pressure_pa", "关闭静压", "p_0", "Pa"),
            ("back_pressure_pa", "背压", "p_b", "Pa"),
        ]:
            row(label, symbol, data[key], unit, "书稿 5.3.1")
        body += [
            "引用书稿式 (5-5)，假定二次风机曲线：",
            "",
            f"$$Q=Q_0\\sqrt{{1-p_b/p_0}}={data['free_flow_m3_h']}\\sqrt{{1-{data['back_pressure_pa']}/{data['shutoff_pressure_pa']}}}={result['flow_m3_s'] * 3600:.3f}\\;\\mathrm{{m^3/h}}$$",
            "",
            f"风量为自由风量的 {result['fraction'] * 100:.3f}%。本例仅为曲线近似，不代表真实设备数据。",
            "**敏感性说明：** 背压为原值的 0.8、1、1.2 倍时，风量比例依次为 "
            + "、".join(f"{x * 100:.2f}%" for x in result["sensitivity"].values())
            + "。",
        ]
    elif module == "p2_dwelling":
        fields = [
            ("bedrooms", "卧室数", "N", "间"),
            ("volume_m3", "户内容积", "V", "m³"),
            ("n50_per_h", "气密性", "n_{50}", "h⁻¹"),
            ("kitchen_open", "开敞厨房", "K", "—"),
            ("door_gap_area_m2", "每门缝面积", "A_d", "m²"),
            ("transfer_area_m2", "每过流口面积", "A_t", "m²"),
            ("density_kg_m3", "空气密度", r"\rho", "kg/m³"),
            ("hood_m3_h", "油烟机风量", "Q_h", "m³/h"),
            ("fresh_supply_m3_h", "新风送风量", "Q_s", "m³/h"),
            ("fresh_exhaust_m3_h", "新风排风量", "Q_e", "m³/h"),
            ("opening_area_m2", "补风口面积", "A_o", "m²"),
            ("mechanical_makeup_m3_h", "机械补风量", "Q_m", "m³/h"),
            ("threshold_pa", "燃气具区负压提示阈值", "p_l", "Pa"),
        ]
        for key, label, symbol, unit in fields:
            row(
                label,
                symbol,
                "、".join(map(str, data[key]))
                if isinstance(data[key], list)
                else ("否" if data[key] is False else data[key]),
                unit,
                "书稿 5.3.2；可配置提示值" if key == "threshold_pa" else "假设，需作者确认",
            )
        row("孔口流量系数", "C_d", 0.6, "—")
        row("围护缝隙指数", "n", 0.65, "—")
        body += [
            "使用 M2 稳态多区质量平衡与围护幂律，围护缝隙均分，内门过流按孔口计算；油烟机及新风设备按理想定风量。",
            "",
            "| 气密性 h⁻¹ | 方案 | 厨房压力 Pa | 起居室压力 Pa | 补风口流入 m³/h | 超过负压阈值 |",
            "|---:|---|---:|---:|---:|---|",
        ]
        names = {
            "no_makeup": "无补风",
            "interlock": "联锁关闭新风排风",
            "opening": "自然补风口（起居室）",
            "opening_kitchen": "自然补风口（厨房）",
            "mechanical_living": "机械补风（起居室）",
            "mechanical_kitchen": "机械补风（厨房）",
        }
        for n, scenarios in result["scenarios"].items():
            for mode, val in scenarios.items():
                body.append(
                    f"| {n} | {names[mode]} | {val['pressures_pa'][val['gas_zone']]:.3f} | {val['pressures_pa']['living']:.3f} | {val['opening_m3_s'] * 3600:.3f} | {'是' if val['negative_pressure_warning'] else '否'} |"
                )
        body += [
            "",
            f"各工况油烟机设于 {data['hood_room']}，新风送风设于 {data['supply_room']}，新风排风设于 {data['exhaust_room']}，卫生间排风扇设于 {data['bath_fan_room']}（本例关闭）；补风口或机械补风位置见方案名称。房间代号 living 为起居室、kitchen 为厨房、bath 为卫生间。",
            "**敏感性说明：** 两档气密性及不同补风位置见上表。结果依赖缝隙分布、设备风量与门状态；未计风机背压、烟道倒灌，不能替代燃气安全检查。",
        ]
    elif module == "p2_infiltration":
        fields = [
            ("volume_m3", "户内容积", "V", "m³"),
            ("n50_per_h", "气密性", "n_{50}", "h⁻¹"),
            ("exponent", "缝隙指数", "n", "—"),
            ("inside_temperature_k", "室内温度", "T_i", "K"),
            ("outside_temperature_k", "室外温度", "T_o", "K"),
            ("absolute_pressure_pa", "大气压力", "p_a", "Pa"),
            ("height_m", "缝隙高差", "H", "m"),
            ("cp_windward", "迎风面风压系数", "C_{p1}", "—"),
            ("cp_leeward", "背风面风压系数", "C_{p2}", "—"),
            ("wind_speed_m_s", "风速", "u", "m/s"),
        ]
        for key, label, symbol, unit in fields:
            row(label, symbol, data[key], unit)
        body += [
            "将总缝隙系数按两立面等分，在不同高度计算风压与热压；稳态质量流入量按室内密度换算为室内容积流量。",
            "",
            "$$C=n_{50}V/50^n,\\quad p_w=C_p\\rho_o u^2/2,\\quad n_{inf}=\\dot m_{in}/(\\rho_iV)$$",
            "",
            f"计算结果：自然渗透换气次数 {result['design']['air_change_per_s'] * 3600:.3f} h⁻¹；不是实测值。",
            "书稿 3.5.2 所述北京及上海样本中，北京样本多数为 0.1～0.3 h⁻¹，最低约 0.09 h⁻¹；本工况低于该多数区间。气象、气密性、房间及测量时段不同，不能据此验证或推翻实测结论。",
            "**敏感性说明：** 风速 "
            + "、".join(
                f"{v} m/s 时 {x['air_change_per_s'] * 3600:.3f} h⁻¹"
                for v, x in result["sensitivity"].items()
            )
            + "；仅为固定风向和温差的示例。",
        ]
    else:
        s = result["stack"]
        ins = data["zones"][data["stack"]["inside"]]
        out = data["zones"][data["stack"]["outside"]]
        links = data["links"]
        row("竖井高度", "H", data["stack"]["height_m"], "m", "书稿 5.2.1")
        row("竖井温度", "T_i", ins["temperature_k"], "K", "书稿 5.2.1（20 ℃）")
        row("室外温度", "T_o", out["temperature_k"], "K", "书稿 5.2.1（−10 ℃）")
        row("大气压力", "p_a", data["pressure_pa"], "Pa")
        for i, x in enumerate(links, 1):
            row(f"开口{i}面积", f"A_{i}", x["area_m2"], "m²")
            row(f"开口{i}流量系数", f"C_{{d{i}}}", x["discharge"], "—")
            row(f"开口{i}高度", f"z_{i}", x["height_m"], "m")
        row("孔口计算参考密度", r"\rho_r", links[0]["reference_density"], "kg/m³")
        body += [
            "采用干空气状态方程及静压近似，g=9.81 m/s²，R=287.055 J/(kg·K)；上下开口面积相等是示例假设。",
            "",
            "$$\\Delta p_{总}=gH(\\rho_o-\\rho_i),\\quad z_n=-p_i(0)/[g(\\rho_o-\\rho_i)]$$",
            "",
            f"精确计算总热压 {s['total_pressure_pa']:.3f} Pa，中和面距底 {s['neutral_height_m']:.3f} m；下开口压差 {result['flows'][0]['delta_p']:.3f} Pa，上开口压差 {result['flows'][1]['delta_p']:.3f} Pa（按路径起点减终点）。",
            f"书稿式 (5-4) 简化值：0.04×{data['stack']['height_m']}×{abs(ins['temperature_k'] - out['temperature_k']):g}={s['simplified_pa']:.3f} Pa。总热压不能直接等同某开口的有效压差；原文约 40 Pa 不可不加路径条件地通用。",
            "**敏感性说明：** 上开口面积按 0.8、1.2 倍变化时，中和面分别为 "
            + "、".join(f"{v:.3f} m" for v in s["opening_sensitivity"].values())
            + "；实际开口大小与路径需现场确定。",
        ]
    return "\n".join(rows + body + ["", "本例不涉及条文判定。", ""])
