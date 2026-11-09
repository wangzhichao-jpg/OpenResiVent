"""M4 书稿片段；参数来源、近似与局限明确呈现。"""


def render_recovery(module: str, d: dict, r: dict) -> str:
    """算例输入与结果 → Markdown 计算片段。"""
    rows = ["| 参数 | 符号 | 数值 | 单位 | 来源 |", "|---|---|---:|---|---|"]

    def row(name, symbol, value, unit, source):
        rows.append(f"| {name} | ${symbol}$ | {value} | {unit} | {source} |")

    body = ["", "**第一步：计算。**", ""]
    if module == "m4_fouling":
        row("恒定送风量", "Q", d["flow_m3_h"], "m³/h", "论文2第7页额定风量；恒流为假设，需作者确认")
        row("捕集效率", "E", f"{d['capture_efficiency'] * 100:g}", "%", "假设，需作者确认")
        row("固定风量下阻力倍率", "r", d["pressure_ratio"], "—", "论文2第6页")
        for c, v in d["pm10_ug_m3"].items():
            row(
                {"beijing": "北京", "shanghai": "上海", "harbin": "哈尔滨"}[c] + " PM10",
                "C",
                v,
                "μg/m³",
                "论文2第9页表5",
            )
        body += [
            "按论文2第6页式(9)的积尘指数，先求**相同风量**下阻力翻倍所需积尘；再假设污染物浓度、风量和捕集率恒定。",
            "",
            r"$$M_g=\frac{\ln r}{\ln 1.026994},\quad t_h=\frac{10^6 M_g}{C_{\mu g/m^3} E Q_{m^3/h}}$$",
            "",
            f"相同风量下阻力翻倍的积尘 {r['doubling_dust_kg'] * 1000:.3f} g。",
            "",
            "| 城市 | 恒流简化周期 d | 读图动态周期 d | 论文动态模拟周期 d |",
            "|---|---:|---:|---:|",
        ]
        literature = {"beijing": 71, "shanghai": 81, "harbin": 64}
        names = {"beijing": "北京", "shanghai": "上海", "harbin": "哈尔滨"}
        for c, v in r["cities"].items():
            body.append(
                f"| {names[c]} | {v['period_s'] / 86400:.2f} | {v['dynamic_period_s'] / 86400:.2f} | {literature[c]} |"
            )
        dynamic = r["dynamic_figure"]
        body.append(
            f"论文2图3/图5风机及机箱读图、表1额定管外阻力示例：动态阻力达设定倍率对应积尘 {dynamic['dust_kg'] * 1000:.2f} g，送风量从 {dynamic['clean']['flow_m3_s'] * 3600:.1f} 降至 {dynamic['dirty']['flow_m3_s'] * 3600:.1f} m³/h（占初始 {dynamic['flow_ratio'] * 100:.2f}%）；图点误差及假设见 M4 趋势检验。"
        )
        s = r["cities"]["beijing"]["sensitivity_s"]
        body += [
            "",
            f"**敏感性说明：** 北京风量按基准的 0.8、1.2 倍时周期分别为 {s['0.8'] / 86400:.2f}、{s['1.2'] / 86400:.2f} d。论文中风机工况与风量随积尘变化，动态压降翻倍积尘约 34.2 g，与此恒流公式不同。书稿约 97 d 未提供充分参数，不能据此判定与 71 d 的确切换算关系。",
        ]
    elif module == "m4_frost":
        row("室外温度", "t_o", d["outdoor_c"], "℃", "论文4第2–3页实验条件")
        row("排风温度", "t_e", d["indoor_c"], "℃", "论文4第2–3页实验条件")
        row("室外相对湿度", "RH_o", d["outdoor_rh"] * 100, "%", "论文4第2页实验条件")
        row("排风相对湿度", "RH_e", d["extract_rh"] * 100, "%", "论文4第3页实验条件")
        row("设计风量", "Q", d["flow_m3_h"], "m³/h", "论文4第9页实验工况")
        row(
            "初始显热效率",
            "\\eta_s",
            f"{d['sensible_efficiency'] * 100:g}",
            "%",
            "假设，需作者确认",
        )
        row("比较时长", "t", d["duration_h"], "h", "假设，需作者确认")
        z = r["strategies"]
        body += [
            f"按论文4第11页图11在室外相对湿度 {d['outdoor_rh'] * 100:.0f}% 读图插值，阈值约 {r['figure11_threshold_m3_s'] * 3600:.1f} m³/h（约 ±5 m³/h）；第5–6页图4同类实验工况报道约 64 m³/h。图10另在室外相对湿度 45% 下给出约 {r['figure10_threshold_m3_s'] * 3600:.1f} m³/h，不能混为同一工况。",
            "",
            "| 策略 | 送风量 m³/h | 预热电耗 kWh | 可回收显热 kWh | 回收量相对损失 |",
            "|---|---:|---:|---:|---:|",
        ]
        for key, label in [("preheat", "预热至0℃"), ("reduce_flow", "降风量"), ("bypass", "旁通")]:
            x = z[key]
            body.append(
                f"| {label} | {x['supply_m3_s'] * 3600:.1f} | {x['electric_j'] / 3.6e6:.3f} | {x['recovery_j'] / 3.6e6:.3f} | {x['recovery_loss_fraction'] * 100:.1f}% |"
            )
        body += [
            "",
            "**敏感性说明：** 论文图10固定室外相对湿度45%，排风相对湿度45%/55%时的读图阈值分别为 "
            + f"{r['sensitivity']['0.45'] * 3600:.0f}/{r['sensitivity']['0.55'] * 3600:.0f} m³/h。预热、降风量仅做稳态显热估算，未模拟除霜动态；降风需核验室内通风。",
        ]
    elif module == "m4_assess":
        for key, name, symbol, unit in [
            ("sensible_heat", "显热制热效率", "\\eta_{sh}", "—"),
            ("sensible_cool", "显热制冷效率", "\\eta_{sc}", "—"),
            ("total_heat", "全热制热效率", "\\eta_{th}", "—"),
            ("total_cool", "全热制冷效率", "\\eta_{tc}", "—"),
            ("specific_power_w_per_m3h", "单位风量耗功率", "SFP", "W/(m³/h)"),
        ]:
            row(
                name,
                symbol,
                f"{d[key] * 100:g}" if key != "specific_power_w_per_m3h" else d[key],
                "%" if key != "specific_power_w_per_m3h" else unit,
                "假设，需作者确认",
            )
        body += [
            "对显热型近零能耗档、全热型一般住宅档分别做示例初筛；两者对应不同产品类型，不将两种效率同时强加于同一产品。",
            "",
        ]
        for name in ("near_zero", "general"):
            for check in r[name]["checks"]:
                key = check["id"]
                if key.endswith(":sfp"):
                    label = "GB/T 51350-2019 第 6.2.8 条（单位风量耗功率）"
                    measure = (
                        f"测得 {check['value']:.2f} W/(m³/h)，限值 {check['limit']:.2f} W/(m³/h)"
                    )
                else:
                    label = {
                        "GBT51350-2019:6.2.7:sensible": "GB/T 51350-2019 第 6.2.7 条（显热交换效率）",
                        "GBT51350-2019:6.2.7:total": "GB/T 51350-2019 第 6.2.7 条（全热交换效率）",
                        "GBT21087-2020:total_heat": "GB/T 21087-2020（制热全热效率）",
                        "GBT21087-2020:total_cool": "GB/T 21087-2020（制冷全热效率）",
                        "GBT21087-2020:sensible_heat": "GB/T 21087-2020（制热显热效率）",
                        "GBT21087-2020:sensible_cool": "GB/T 21087-2020（制冷显热效率）",
                    }[key]
                    measure = f"测得 {check['value'] * 100:g}%，限值 {check['limit'] * 100:g}%"
                body.append(f"- {label}：{measure}，{'满足' if check['passed'] else '不满足'}。")
        body += [
            "",
            "GB/T 51350-2019 第 6.2.7、6.2.8 条按显热型判定；GB/T 21087-2020，条号与原文待核，适用条件待核。仅为单项初筛，不能替代产品认证。",
            "**敏感性说明：** 临近阈值时应考虑额定测试工况和测量不确定度。",
        ]
    else:
        row("芯体类型", "K", "纤维素基膜", "—", "假设，需作者确认")
        row("初始潜热效率", "\\eta_0", f"{d['initial_latent'] * 100:g}", "%", "假设，需作者确认")
        row(
            "清洗后潜热效率",
            "\\eta_c",
            f"{d['after_clean_latent'] * 100:g}",
            "%",
            "假设，需作者确认",
        )
        x = r["result"]
        body += [
            f"清洗后效率下降比例为 {x['post_clean_decline'] * 100:.2f}%，{'超过' if x['replace_recommended'] else '未超过'} 20% 的书稿研究建议阈值；{'可考虑更换' if x['replace_recommended'] else '暂不据此建议更换'}。",
            x["method"],
            "依据书稿4.4.2；运维参照 JG/T 400-2025 并遵循设备说明书，不把研究建议冒充标准强制条文。",
            "**敏感性说明：** 清洗后效率分别为基值的 0.95 和 1.05 倍时，衰减比例为 "
            + "、".join(f"{v['post_clean_decline'] * 100:.2f}%" for v in r["sensitivity"].values())
            + "。",
        ]
    if module != "m4_assess":
        body += ["", "本例不涉及条文判定。"]
    return "\n".join(rows + body) + "\n"
