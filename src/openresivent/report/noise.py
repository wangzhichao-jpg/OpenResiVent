"""倍频程噪声书稿演算；示例声学性能并非设备实测。"""


def render_noise(data: dict, result: dict) -> str:
    """输入 SI 工况及频谱结果 → 带详细过程的 Markdown。"""
    rows = ["| 参数 | 符号 | 数值 | 单位 | 来源 |", "|---|---|---:|---|---|"]
    for label, symbol, value, unit, source in [
        (
            "参考风量",
            "Q_0",
            f"{data['reference_flow_m3_s'] * 3600:.6g}",
            "m³/h",
            "假设，需作者确认",
        ),
        (
            "风机倍频程声功率级",
            "L_{w,0}",
            ", ".join(map(str, data["fan_power_db"]))
            if "fan_power_db" in data
            else "由风机比声功率和频谱偏移估算",
            "dB",
            "假设，需作者确认",
        ),
        ("流量指数", "n", data.get("flow_exponent", 5), "—", "假设，需作者确认"),
        ("指向因子", "D", data["directivity"], "—", "假设，需作者确认"),
        ("声源距离", "r", data["distance_m"], "m", "假设，需作者确认"),
        ("房间常数", "R", data["room_constant_m2"], "m²", "假设，需作者确认"),
        (
            "声级目标",
            "L_{lim}",
            data["target_db"],
            "dB(A)",
            data.get("target_kind", "假设，需作者确认")
            if data["target_db"] == 33
            and data.get("target_kind") == "GB 55016-2021 第2.1.4条表2.1.4 睡眠空间设备声"
            else "假设，需作者确认",
        ),
    ]:
        rows.append(f"| {label} | ${symbol}$ | {value} | {unit} | {source} |")
    rows.append(
        f"| 运行风量 | $Q$ | {', '.join(f'{x * 3600:.6g}' for x in data['flows_m3_s'])} | m³/h | 假设，需作者确认 |"
    )
    labels = {"straight": "直管", "bend": "弯头", "silencer": "消声器"}
    for i, stage in enumerate(data["stages"], 1):
        name = labels[stage["kind"]]
        rows.append(
            f"| {name}{i}倍频程衰减 | $\\Delta L_{{{i}}}$ | {', '.join(map(str, stage['attenuation_db']))} | dB | 假设，需作者确认 |"
        )
        if stage.get("regenerated_db") is not None:
            rows.append(
                f"| {name}{i}再生声功率 | $L_{{r{i}}}$ | {', '.join(map(str, stage['regenerated_db']))} | dB | 假设，需作者确认 |"
            )
    rows.append(
        f"| 末端反射损失 | $\\Delta L_t$ | {', '.join(map(str, data['terminal_reflection_db']))} | dB | 假设，需作者确认 |"
    )
    if data.get("diffuser_regenerated_db") is not None:
        rows.append(
            f"| 风口再生声功率 | $L_d$ | {', '.join(map(str, data['diffuser_regenerated_db']))} | dB | 假设，需作者确认 |"
        )
    if "fan_power_db" not in data:
        rows.extend(
            [
                f"| 风机静压 | $p$ | {data['fan_pressure_pa']} | Pa | 假设，需作者确认 |",
                f"| 比声功率系数 | $K$ | {data['fan_specific_level_db']} | dB | 假设，需作者确认 |",
                f"| 倍频带偏移 | $d_i$ | {', '.join(map(str, data['fan_octave_offsets_db']))} | dB | 假设，需作者确认 |",
            ]
        )
    rows += [
        "",
        "**第一步：计算。**",
        r"$$L_p=L_w+10\lg[D/(4\pi r^2)+4/R],\quad L_A=10\lg\sum_i 10^{(L_{p,i}+A_i)/10}$$",
        "八个倍频程中心依次为 63、125、250、500、1000、2000、4000、8000 Hz。风机声功率按风量指数缩放；各段先扣除衰减，再以能量叠加再生声，最后考虑出口反射和风口再生声。",
        "| 风量 m³/h | A 声级 dB(A) | 睡眠空间设备声限值判断 |",
        "|---:|---:|---|",
    ]
    for row, check in zip(result["settings"], result["checks"], strict=True):
        rows.append(
            f"| {row['flow_m3_s'] * 3600:.2f} | {row['a_weighted_db']:.2f} | {'未超过' if check['passed'] else '超过'} 33 dB(A) |"
        )
    rows += [
        f"目标 {result['target_db']:.2f} dB(A) 时最大风量为 {result['maximum_flow_m3_s'] * 3600:.2f} m³/h，代回 {result['at_maximum_db']:.2f} dB(A)。",
        "方法示意，参数为假设；各声源频谱、衰减、再生声与流量指数均需作者确认。未计结构传声与背景声，不构成现场验收。",
        "**敏感性说明：** 多档风量反映声级对风量的敏感性，设备频谱及末端衰减也须现场或产品检测核实。",
        "条文判定：按 GB 55016-2021 第2.1.4条表2.1.4 的睡眠空间设备声限值作单声源初筛；完整合规需合并其他设备声并考虑测量条件。",
    ]
    return "\n".join(rows) + "\n"
