"""将计算结果生成可复核的 Markdown 演算片段。"""

import math
import re

import yaml

from openresivent.core.provenance import parameter_data_path


def _display_number(value: float, digits: int) -> str:
    """按有效数字显示，普通工程数量级禁止科学记数。"""
    text = format(value, f".{digits}g")
    if "e" in text.lower() and 1e-4 <= abs(value) < 1e7:
        from decimal import Decimal

        return format(Decimal(text), "f")
    return text


def _scientific_latex(text: str) -> str:
    """将数值科学记数转换为 LaTeX，数学环境内不额外嵌套美元符。"""
    pattern = re.compile(r"(?<![\w.])([+-]?(?:\d+(?:\.\d*)?|\.\d+))[eE]([+-]?\d+)(?![\w.])")

    def convert(part, in_math):
        def repl(match):
            expr = match.group(1) + r"\times 10^{" + str(int(match.group(2))) + "}"
            return expr if in_math else "$" + expr + "$"

        return pattern.sub(repl, part)

    pieces = re.split(r"(\$\$.*?\$\$|\$[^$\n]*\$)", text, flags=re.DOTALL)
    return "".join(convert(part, part.startswith("$")) for part in pieces)


def _input_rows(inputs: dict, module: str) -> list[str]:
    """生成输入明细；数值来源未知时不冒称书稿或实测。"""
    rows = []
    with parameter_data_path("param_meta.yaml").open(encoding="utf8") as stream:
        metadata = yaml.safe_load(stream)
    units = {
        "m2": "m²",
        "m3": "m³",
        "m_s": "m/s",
        "m3_h": "m³/h",
        "l_h_person": "L/(h·人)",
        "mg_m2_h": "mg/(m²·h)",
        "mg_m3": "mg/m³",
        "ug_m3": "μg/m³",
        "ng_m3": "ng/m³",
        "ppm": "ppm",
        "elapsed_s": "s",
        "elapsed_h": "h",
        "background": "ppm",
        "initial": "ppm",
        "final": "ppm",
    }

    def walk(value, path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in (
                    "source",
                    "assumption",
                    "assumptions",
                    "csv",
                    "start",
                    "seed",
                    "worst_day_indexes",
                    "hcho_sensitivity",
                    "sensitivity",
                    "noise",
                ) and not key.endswith("_source"):
                    walk(child, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, child in enumerate(value, 1):
                walk(child, f"{path}[{index}]")
        elif not (module == "tracer" and path == "csv"):
            key = path.rsplit(".", 1)[-1]
            key = re.sub(r"\[\d+\]$", "", key)
            if key in ("csv", "assumptions", "start", "seed", "worst_day_indexes"):
                return
            unit = next(
                (v for k, v in sorted(units.items(), key=lambda x: -len(x[0])) if key.endswith(k)),
                "—",
            )
            if unit == "—" and key.endswith("_s"):
                unit = "s"
            elif unit == "—" and key.endswith("_h"):
                unit = "h"
            elif unit == "—" and "concentration" in key:
                unit = "体积分数"
            source = "假设，需作者确认"
            if module == "tracer" and (path.startswith("two_point.") or path == "background"):
                source = "书稿原文 6.2.1"
            elif module == "co2" and key in (
                "occupants",
                "co2_l_h_person",
                "co2_outdoor_ppm",
                "co2_limit_ppm",
            ):
                source = "书稿原文 2.3.2"
            elif (
                key == "limit_ppm"
                and value == 1000
                and inputs.get("limit_ppm_source") == "GB/T 18883-2022 第4.2条、表1"
            ):
                source = inputs["limit_ppm_source"]
            elif key == "hcho_limit_mg_m3" and value == 0.08:
                source = "标准条文 GB/T 18883-2022 表 1"
            if key not in metadata:
                raise ValueError(f"缺少参数元数据：{key}")
            meta = metadata[key]
            unit = meta["unit"]
            text = (
                _display_number(value, meta["digits"])
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else {"sedentary": "久坐"}.get(str(value), str(value))
            )
            text = text.replace("|", "\\|")
            label, symbol = meta["name"], meta["symbol"]
            if key == "area_m2":
                match = re.search(r"bedrooms\[(\d+)\]", path)
                if "hcho_materials" in path:
                    label, symbol = "材料面积", r"A_{m" + (match.group(1) if match else "") + "}"
                elif match:
                    label, symbol = f"卧室{match.group(1)}面积", r"A_{" + match.group(1) + "}"
                elif path.startswith("living."):
                    label, symbol = "起居室面积", r"A_{l}"
                elif path == "area_m2":
                    label, symbol = "居住面积", "F"
            rows.append(f"| {label} | ${symbol}$ | {text} | {unit} | {source} |")

    walk(inputs)
    return rows


def _duct_rows(inputs: dict) -> list[str]:
    """生成风管算例输入表，原始算例采用工程单位。"""
    source = "假设，需作者确认"
    rows = [
        f"| 设计总风量 | $Q$ | {inputs['design_flow_m3_h']} | m³/h | {source} |",
        f"| 空气密度 | $\\rho$ | {inputs['density_kg_m3']} | kg/m³ | {source} |",
        f"| 运动黏度 | $\\nu$ | {inputs['kinematic_viscosity_m2_s']} | m²/s | {source} |",
    ]
    for segment in inputs["segments"]:
        for field, label, symbol, unit in [
            ("flow_m3_h", "风量", "Q", "m³/h"),
            ("length_m", "长度", "L", "m"),
            ("roughness_m", "绝对粗糙度", "k", "m"),
            ("diameter_m", "直径", "D", "m"),
            ("width_m", "宽度", "a", "m"),
            ("height_m", "高度", "b", "m"),
            ("local_zeta", "局部阻力系数", "\\zeta", "—"),
        ]:
            if field in segment:
                rows.append(
                    f"| {segment['name']}{label} | ${symbol}$ | {segment[field]} | {unit} | {source} |"
                )
    if "fan" in inputs:
        rows += [
            f"| 风机自由风量 | $Q_0$ | {inputs['fan']['free_flow_m3_h']} | m³/h | {source} |",
            f"| 风机关闭压力 | $p_0$ | {inputs['fan']['shutoff_pressure_pa']} | Pa | {source} |",
        ]
    return rows


def render(title: str, module: str, inputs: dict, result: dict) -> str:
    """题目、模块、输入与 SI 结果 → Markdown 文本，不改变计算单位。"""
    from openresivent.core.module_names import internal

    module = internal(module)
    if module == "makeup_design":
        return f"机械补风 {result['mechanical']['value'] * 3600:.4f} m³/h；自然开口 {result['opening']['value'] * 10000:.4f} cm²。示例负压提示值不是安全限值。\n"
    if module == "duct_noise":
        from openresivent.report.noise import render_noise

        return _scientific_latex(render_noise(inputs, result))
    if module == "shaft":
        return "\n".join(
            ["### 竖井计算", "参数为示例或用户输入，需复核。"]
            + [
                f"- {r['floor']} 层排风 {r['exhaust_m3_s'] * 3600:.2f} m³/h，倒灌 {r['backflow_m3_s'] * 3600:.2f} m³/h。"
                for r in result["floors"]
            ]
        )
    if module == "cfd_compare":
        from openresivent.cfd.report import render as render_cfd

        return _scientific_latex(render_cfd(result))
    if module.startswith("p303_"):
        from openresivent.report.p303 import render as render_p303

        return _scientific_latex(render_p303(module, inputs, result))
    if module == "product_test":
        from openresivent.report.product import render as render_product

        return _scientific_latex(render_product(inputs, result))
    if module.startswith("p3_"):
        from openresivent.report.p3 import render as render_p3

        return _scientific_latex(render_p3(module, inputs, result))
    if module.startswith("m4_"):
        from openresivent.report.recovery import render_recovery

        return _scientific_latex(render_recovery(module, inputs, result))
    if module in ("energy_erv", "energy_control"):
        from openresivent.report.energy import render_energy

        return _scientific_latex(render_energy(module, inputs, result))
    if module.startswith("p2_") or (
        module == "network"
        and "opening_sensitivity" in result.get("stack", {})
        and all(
            all(k in item for k in ("area_m2", "discharge", "reference_density", "height_m"))
            for item in inputs["links"]
        )
    ):
        from openresivent.report.p2 import render_p2

        return _scientific_latex(render_p2(module, inputs, result))
    lines = [f"### {title}", ""]
    if module == "duct_network":
        lines += [
            "依据：书稿 4.1.3 及 JGJ/T 440-2018 第 4.5.2、4.5.3、5.2.1 条。",
            "",
            "各管段计算结果：",
            "",
            "| 管段 | 风速 m/s | 沿程 Pa | 局部 Pa | 宜项 |",
            "|---|---:|---:|---:|---|",
        ]
        for name, values in result["segments"].items():
            lines.append(
                f"| {name} | {values['velocity_m_s']:.3g} | {values['friction_pa']:.3g} | {values['local_pa']:.3g} | {'满足' if values['recommended_speed_passed'] else '不满足'} |"
            )
        for name, values in result["segments"].items():
            lines.append(
                f"{name}风速 {values['velocity_m_s']:.3g} m/s，{'满足' if values['maximum_speed_passed'] else '不满足'} JGJ/T 440-2018 第 4.5.2 条不超过 6.0 m/s 的要求。"
            )
        for name, check in result["imbalance"].items():
            lines.append(
                f"环路{name}压损 {result['route_losses_pa'][name]:.3g} Pa，不平衡率 {check['fraction'] * 100:.3g}%，{'满足' if check['recommended_passed'] else '不满足'} JGJ/T 440-2018 第 4.5.3 条宜不大于 15% 的要求。"
            )
        lines += [
            f"最不利环路：{result['critical_route']}，压损 {result['pressure_pa']:.3g} Pa。",
            f"风量附加后范围：{result['fan_allowance']['flow_m3_s'][0] * 3600:.3g}～{result['fan_allowance']['flow_m3_s'][1] * 3600:.3g} m³/h；风压范围：{result['fan_allowance']['pressure_pa'][0]:.3g}～{result['fan_allowance']['pressure_pa'][1]:.3g} Pa。",
            "输入均为示例值，需作者确认；局部阻力和粗糙度应按实际管件核验。",
            "自然平衡各支路风量："
            + "；".join(
                f"{name} {flow * 3600:.3g} m³/h"
                for name, flow in result["balanced"]["terminal_flows_m3_s"].items()
            )
            + "。",
        ]
        if "fan_operating_point" in result:
            op = result["fan_operating_point"]
            lines.append(
                f"风机工作点：{op['flow_m3_s'] * 3600:.3g} m³/h，{op['pressure_pa']:.3g} Pa；效率数据未给出，不作效率条文判断。"
            )
        lines.append(
            "**敏感性说明：** 局阻系数分别取 0.8、1、1.2 倍时，最不利压损为 "
            + "、".join(f"{v:.3g}" for v in result["sensitivity_local_zeta"].values())
            + " Pa。"
        )
    elif module == "co2":
        lines += [
            "依据：书稿式 (2-3)、JGJ/T 440-2018 式 (4.2.2)。",
            "",
            "由式 (2-3) 计算所需新风量。",
            "",
            f"总排放量 $M={inputs['occupants']}\\times{inputs['co2_l_h_person']}={float(inputs['occupants']) * float(inputs['co2_l_h_person']):g}$ L/h。",
            "",
            f"浓度差：$C-C_0=({inputs['co2_limit_ppm']}-{inputs['co2_outdoor_ppm']})\\times 10^{{-6}}={float(inputs['co2_limit_ppm']) - float(inputs['co2_outdoor_ppm']):g}\\times 10^{{-6}}$ L/L。",
            "",
            f"$$ G=\\frac{{M}}{{C-C_0}}=\\frac{{{float(inputs['occupants']) * float(inputs['co2_l_h_person']):g} \\text{{ L/h}}}}{{{float(inputs['co2_limit_ppm']) - float(inputs['co2_outdoor_ppm']):g}\\times10^{{-6}}}}={result['flow_m3_s'] * 3600 * 1000:.6g} \\text{{ L/h}}={result['flow_m3_s'] * 3600:.6g} \\text{{ m}}^3/\\text{{h}} \\tag{{2-4}} $$",
            "",
            f"结果：{result['flow_m3_s'] * 3600:.6g} m³/h。",
            "",
            "条文判定：本例仅展示 CO₂ 路径，未完成全户综合校核。",
        ]
    elif module == "ventrate":
        lines += [
            "依据：JGJ/T 440-2018 第 4.2.1–4.2.3、5.2.1 条；人员法另见所启用规则包。",
            "",
            "$$ Q_d=\\max(Fhn,\\sum Q_{卧}+Q_{起},Q_{B,户}) \\tag{M1-1} $$",
            "",
            f"代入：居住面积 {inputs['area_m2']} m²，净高 {inputs['height_m']} m；全户换气次数法 {result['whole_A'] * 3600:.4f} m³/h，房间合计 {result['room_total'] * 3600:.4f} m³/h。",
            "",
            "| 路径 | 来源 | 结果 m³/h |",
            "|---|---|---:|",
        ]
        for i, room in enumerate(result["bedrooms"], 1):
            for key in ("A", "B", "C", "D", "selected"):
                if room[key] is not None:
                    source = result["sources"].get(key, "取大值")
                    lines.append(
                        f"| 卧室{i} {('取大值' if key == 'selected' else key)} | {source} | {room[key] * 3600:.3g} |"
                    )
        for key in ("A", "B", "D"):
            if result["living"][key] is not None:
                lines.append(
                    f"| 起居室 {key} | {result['sources'][key]} | {result['living'][key] * 3600:.4f} |"
                )
        if result["whole_D"]:
            lines.append(f"| 全户 D | {result['sources']['D']} | {result['whole_D'] * 3600:.4f} |")
        if result["whole_B"] is not None:
            lines.append(f"| 全户 B | {result['sources']['B']} | {result['whole_B'] * 3600:.4f} |")
        lines += [
            f"| 全户设计 | {result['sources']['design']} | {result['design'] * 3600:.4f} |",
            f"| 仅 440 设计 | JGJ/T 440-2018 4.2.3 | {result['only_440'] * 3600:.4f} |",
            f"| 风机风量 | {result['sources']['fan']} | {result['fan'] * 3600:.4f} |",
            "",
            "条文判定：",
        ]
        lines.extend(
            f"- {x['id']}：{'通过' if x['passed'] else '不通过'}；{x['explanation']}。"
            for x in result["checks"]
        )
        lines.extend(
            [
                "",
                f"ASHRAE 62.2-2025 对比：{result['international']['ashrae_m3_s'] * 3600:.4f} m³/h。",
            ]
        )
        n_h = result["rate_per_s"] * 3600
        lines += [
            "",
            "各路径代入：",
            "",
            "$$Q_A=Fhn,\\quad Q_B=30N,\\quad Q_C=\\frac{M}{C-C_0},\\quad Q_D=\\frac{\\sum EF_iA_i}{C_{lim}-C_0} \\tag{M1-2}$$",
            "",
        ]
        for idx, (source, room) in enumerate(
            zip(inputs["bedrooms"], result["bedrooms"], strict=True), 1
        ):
            delta = (
                float(inputs.get("limit_ppm", 1000)) - float(inputs.get("outdoor_ppm", 400))
            ) * 1e-6
            emission_l_h = room["C"] * delta * 3600 * 1000
            lines.append(
                f"- 卧室 {idx}：$Q_A={source['area_m2']}\\times{source['height_m']}\\times{n_h:.6g}={room['A'] * 3600:.6g}$ m³/h；CO₂ 总排放 {emission_l_h:.6g} L/h，$Q_C=({emission_l_h:.6g}/1000)/{delta:.6g}={room['C'] * 3600:.6g}$ m³/h。"
            )
            if room["B"] is not None:
                lines.append(
                    f"  $Q_B=30\\times{source['occupants']}={room['B'] * 3600:.6g}$ m³/h。"
                )
            if room["D"]:
                material = source.get("hcho_materials", [])
                source_mg_h = sum(float(x["ef_mg_m2_h"]) * float(x["area_m2"]) for x in material)
                difference = float(inputs.get("hcho_limit_mg_m3", 0.08)) - float(
                    inputs.get("hcho_outdoor_mg_m3", 0.01)
                )
                lines.append(
                    f"  甲醛散发量 $M=\\sum EF_i A_i={source_mg_h:.6g}$ mg/h；$Q_D={source_mg_h:.6g}/{difference:.6g}={room['D'] * 3600:.6g}$ m³/h。"
                )
        generation_l_h = result["international"]["en_generation_m3_s"] * 3600 * 1000
        lines.extend(
            [
                "",
                f"ASHRAE：$Q=0.15\\times{inputs['floor_area_m2']}+3.5\\times({len(inputs['bedrooms'])}+1)={result['international']['ashrae_m3_s'] * 1000:.6g}$ L/s。",
                f"EN 对比使用 CO₂ 总排放 {generation_l_h:.6g} L/h：",
            ]
        )
        for k, excess in [("I", 550), ("II", 800), ("III", 1350)]:
            value = result["international"]["en_m3_s"][k] * 3600
            lines.append(
                f"- EN 16798-1 {k} 级：$Q=({generation_l_h:.6g}/1000)/({excess}\\times10^{{-6}})={value:.6g}$ m³/h。"
            )
        if "hcho_example" in result:
            base = result["bedrooms"][0]
            example = result["hcho_example"]
            material = inputs["bedrooms"][0]["hcho_materials"][0]
            delta = float(inputs["hcho_limit_mg_m3"]) - float(inputs["hcho_outdoor_mg_m3"])
            lines += [
                "",
                "**甲醛散发率对照：** 两组均为示例值，需作者确认。",
                f"第一组：{material['ef_mg_m2_h']} mg/(m²·h) × {material['area_m2']} m² / {delta:g} mg/m³ = {base['D'] * 3600:.2f} m³/h，卧室取 {base['selected'] * 3600:.2f} m³/h，由 CO₂ 法控制。",
                f"第二组：{inputs['hcho_example_ef_mg_m2_h']} mg/(m²·h) × {material['area_m2']} m² / {delta:g} mg/m³ = {example['D'] * 3600:.2f} m³/h，卧室取 {example['selected'] * 3600:.2f} m³/h，由甲醛法控制。",
            ]
        if "hcho_sensitivity" in result:
            lines.append(
                "甲醛源强倍数敏感性（倍数 → 全户设计风量 m³/h）："
                + ", ".join(f"{k}: {v * 3600:.4f}" for k, v in result["hcho_sensitivity"].items())
            )
    elif module == "tracer":
        lines += [
            "依据：书稿式 (6-11) 至 (6-17)。",
            "",
            "由式 (6-12) 计算两点浓度对应的换气次数。",
            "",
            f"代入：初始 {inputs['two_point']['initial']} ppm，末值 {inputs['two_point']['final']} ppm，背景 {inputs['background']} ppm，时间 {inputs['two_point']['elapsed_s']} s = {float(inputs['two_point']['elapsed_s']) / 3600:g} h。",
            "",
        ]
        initial = float(inputs["two_point"]["initial"]) - float(inputs["background"])
        final = float(inputs["two_point"]["final"]) - float(inputs["background"])
        lines += [
            f"由式 (6-12)，$\\ln({initial:g})={math.log(initial):.3f}$，$\\ln({final:g})={math.log(final):.3f}$，",
            f"故 $ACH=({math.log(initial):.3f}-{math.log(final):.3f})/{float(inputs['two_point']['elapsed_s']) / 3600:g}={result['two_point_s_1'] * 3600:.2f}$ h⁻¹。",
            "",
            "本例不涉及条文判定。",
        ]
    elif module == "transient":
        lines.extend(
            [
                "依据：书稿式 2-16 至 2-18。",
                "",
                "$$C(t)=C_s+(C_i-C_s)e^{-Gt/V},\\quad C_s=C_0+M/G \\tag{2-18}$$",
                "",
                f"代入：V={inputs['volume_m3']} m³，G={inputs['flow_m3_h']} m³/h，初始={inputs['initial_ug_m3']} μg/m³，室外={inputs['outdoor_ug_m3']} μg/m³。",
                "",
                f"稳态 {result['steady_kg_m3'] * 1e9:.6g} μg/m³；{inputs['elapsed_h']} h 时 {result['concentration_kg_m3'] * 1e9:.6g} μg/m³；达目标时间 {result['target_time_s'] / 3600:.6g} h，偏差衰减95%时间 {result['time_95_s'] / 3600:.6g} h。",
                "",
                "条文判定：本例为模型计算，不直接作标准检验判定。",
            ]
        )
    elif module == "health_pah":
        lines.extend(
            [
                "依据：书稿式 2-2、2-1a；Yang 等（2024）第8–10页。",
                "",
                "$$ TEQ=\\sum_i C_iTEF_i,\\quad ICR=TEQ\\cdot IUR\\cdot f \\tag{2-2}$$",
                "",
                "代入多环芳烃浓度（ng/m³）："
                + "，".join(
                    f"{name}：{value:g}" for name, value in inputs["concentrations_ng_m3"].items()
                )
                + f"；单位风险 {inputs['iur_per_ug_m3']} (μg/m³)⁻¹。",
                "$$TEQ="
                + "+".join(
                    f"{value}\\times{result['tef_used'][name]}"
                    for name, value in inputs["concentrations_ng_m3"].items()
                )
                + f"={result['teq_kg_m3'] * 1e12:.6g}\\;\\mathrm{{ng/m^3}}$$",
                f"$$ICR=({result['teq_kg_m3'] * 1e9:.6g}\\;\\mu\\mathrm{{g/m^3}})\\times{inputs['iur_per_ug_m3']}\\times{result['exposure_factor']:.6g}={result['icr']:.6g}$$",
                "",
                f"结果：TEQ={result['teq_kg_m3'] * 1e12:.6g} ng/m³，暴露比例={result['exposure_factor']:.6g}，ICR={result['icr']:.6g}；风险类别：{result['risk_category']}。",
                "",
                "浓度倍数敏感性："
                + "，".join(f"{float(k):g} 倍：{v:.3g}" for k, v in result["sensitivity"].items())
                + "。",
                "",
                "条文判定：风险阈值仅作书稿模型分级，不代替法规合规判定。",
            ]
        )
    elif module == "air_age":
        lines.extend(
            [
                "依据：书稿式 6-2、6-8、6-9。",
                "",
                "$$\\eta_a=\\frac{\\tau_n}{2\\bar\\tau} \\tag{6-2}$$",
                "",
                f"代入：局部空气龄 {[round(float(age), 2) for age in result['local_ages_s']]} s，体积 {inputs['volumes_m3']} m³，名义空气龄 {inputs['nominal_age_s']} s。",
                "",
                f"$$\\bar\\tau=\\frac{{\\sum V_i\\tau_i}}{{\\sum V_i}}={result['average_age_s']:.2f}\\;\\mathrm{{s}},\\qquad \\eta_a=\\frac{{{inputs['nominal_age_s']}}}{{2\\times{result['average_age_s']:.2f}}}={100 * result['efficiency']:.2f}\\%$$",
                "",
                f"平均空气龄 {result['average_age_s']:.6g} s；换气效率 {100 * result['efficiency']:.6g}%。",
                "",
                "条文判定：此为评价指标计算，不作标准合格判定。",
            ]
        )
    elif module == "injection":
        lines.extend(
            [
                "依据：书稿式 6-15、6-16、6-20。",
                "",
                "$$Q=\\frac{q}{C_i-C_o} \\tag{6-20}$$",
                "",
                f"代入：浓度 {inputs['indoor_ppm']} − {inputs['outdoor_ppm']} ppm；恒注入 {inputs['injection_l_min']} L/min，恒浓度注入 {inputs['controlled_injection_l_min']} L/min。",
                "",
                f"恒注入风量 {result['injection_flow_m3_s'] * 3600:.6g} m³/h；恒浓度风量 {result['controlled_flow_m3_s'] * 3600:.6g} m³/h。",
                "",
                "条文判定：此为测量数据处理，不作标准合格判定。",
            ]
        )
    elif module == "airflow_measure":
        lines.extend(
            [
                "依据：书稿式 6-18、6-19（单位由 m³/s 换算为 m³/h）。",
                "",
                "$$ Q=\\bar v A,\\qquad Q_{eff}=\\bar v A_{eff} C_d \\tag{6-19} $$",
                "",
                f"代入风管：{inputs['duct_velocity_m_s']} m/s × {inputs['duct_area_m2']} m²；风口：{inputs['terminal_velocity_m_s']} m/s × {inputs['terminal_area_m2']} m² × {inputs['terminal_coefficient']}。",
                "",
                f"结果：风管 {result['duct_m3_s'] * 3600:.6g} m³/h，风口 {result['terminal_m3_s'] * 3600:.6g} m³/h。",
                "",
                "条文判定：此为测量数据处理，不作标准合格判定。",
            ]
        )
    elif module in ("acceptance", "acceptance_synthetic"):
        lines.extend(
            [
                "依据：JGJ/T 440-2018 第7.3.4–7.3.7条、GB 55015-2021 第6.3.13条（转述）。",
                "",
                "$$\\delta=(Q_{实}-Q_{设})/Q_{设}\\times100\\% \\tag{A-1}$$",
                "",
                f"代入总风量：({inputs['total_measured_m3_h']} − {inputs['total_design_m3_h']}) / {inputs['total_design_m3_h']}；风口：({inputs['terminal_measured_m3_h']} − {inputs['terminal_design_m3_h']}) / {inputs['terminal_design_m3_h']}。",
                "",
                f"结果：总偏差 {result['total_flow']['deviation'] * 100:.2f}%，{'通过' if result['total_flow']['passed'] else '不通过'}；风口偏差 {result['terminal_flow']['deviation'] * 100:.2f}%，{'通过' if result['terminal_flow']['passed'] else '不通过'}。",
                "",
                f"室外最不利五日：{result['continuous']['selected_days']}；室内 PM2.5 均值 {result['continuous']['indoor_pm'] * 1e9:.4f} μg/m³；抽检至少 {result['required_homes']} 户。",
                "",
                f"设计轨：PM2.5 {'通过' if result['tracks']['design']['pm25_passed'] else '不通过'}，CO₂ {'通过' if result['tracks']['design']['co2_passed'] else '不通过'}；验收轨：PM2.5 {'通过' if result['tracks']['acceptance']['pm25_passed'] else '不通过'}，CO₂ {'通过' if result['tracks']['acceptance']['co2_passed'] else '不通过'}。",
                f"点检状态：{ {'passed': '通过', 'failed': '不通过', 'retest_required': '待复测'}.get(result['spot']['status'], '需复核') }；如首测不达标且无复测数据则报告待复测。",
                "",
                "注意：设计轨按自然日 PM2.5、逐1小时 CO₂ 窗口判断；验收轨按最不利五日均值。现场条件及复测另行核验。",
            ]
        )
    elif module == "network":
        lines += [
            "依据：书稿式 (3-6)、(3-7) 和 (5-1)。",
            "",
            "$$ \\sum_j \\dot m_{ij}=0,\\quad Q=C_dA\\sqrt{2|\\Delta p|/\\rho}\\operatorname{sign}(\\Delta p) \\tag{3-6} $$",
            "",
            f"输入：{len(inputs['zones'])} 个节点、{len(inputs['links'])} 条连接。",
            "",
        ]
        for i, flow in enumerate(result["flows"], 1):
            lines.append(
                f"- 路径 {i}：压差 {flow['delta_p']:.6g} Pa，风量 {flow['volume_flow']:.6g} m³/s。"
            )
        if "stack" in result:
            lines.append(
                f"- 总热压差 {result['stack']['total_pressure_pa']:.6g} Pa，中和面 {result['stack']['neutral_height_m']:.6g} m。"
            )
        lines += ["", "条文判定：本例为物理模型验证，不作标准合格判定。"]
    else:
        raise ValueError("未知模块")
    # 已编号公式仅在文字中引用，演算式自身不重复编号。
    body = "\n".join(lines[2:])
    body = re.sub(r"\\tag\{(?!2-4\})[^}]+\}", "", body)
    body = (
        body.replace("GBT18883-2022", "GB/T 18883-2022")
        .replace("GBT51350-2019", "GB/T 51350-2019")
        .replace("转述；限值须按输入计算", "")
    )
    body = body.replace("甲醛源强倍数敏感性", "**敏感性说明：** 甲醛源强倍数敏感性").replace(
        "浓度倍数敏感性：", "**敏感性说明：** 浓度倍数敏感性："
    )
    if module == "co2":
        person_flow = result["flow_m3_s"] * 3600 / float(inputs["occupants"])
        body = re.sub(
            r"条文判定：[^\n]*",
            f"人均新风量 {person_flow:.1f} m³/(h·人)，{'满足' if person_flow >= 30 - 1e-9 else '不满足'} GB/T 18883-2022 表 1 的要求。",
            body,
        )
    elif module not in ("ventrate", "acceptance", "acceptance_synthetic"):
        body = re.sub(r"条文判定：[^\n]*", "本例不涉及条文判定。", body)
    body = (
        body.replace("JGJT440-2018:", "JGJ/T 440-2018 第")
        .replace(":outdoor_air", "")
        .replace("，转述", "")
        .replace("，；", "；")
    )
    body = re.sub(r"(?<![\w.])(-?\d+\.\d{4,})(?![\w.])", lambda m: f"{float(m.group()):.3g}", body)
    body = body.replace("条文判定：\n", "**第二步：条文对照。**\n")
    body = re.sub(
        r"^- ([^：\n]+)：(通过|不通过)；([^\n]+)。$",
        r"- \1：\3；该项\2。",
        body,
        flags=re.MULTILINE,
    )
    return _scientific_latex(
        "\n".join(
            [
                "| 参数 | 符号 | 数值 | 单位 | 来源 |",
                "|---|---|---:|---|---|",
                *(_input_rows(inputs, module) if module != "duct_network" else _duct_rows(inputs)),
                "",
                "**第一步：计算。**",
                "",
                body,
            ]
        )
        + "\n"
    )
