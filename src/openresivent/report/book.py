"""将完整演算压缩为书稿正文；完整资料独立留存供复核。"""

import re

from openresivent import __version__


def render_book(
    title: str, case_id: str, chapter: str, full: str, result: dict, inputs: dict | None = None
) -> str:
    """生成四段式正文。详细演算原样进入附录，不修改求解结果。"""
    lines = full.splitlines()
    try:
        start = next(
            i for i, x in enumerate(lines) if x.strip() == "| 参数 | 符号 | 数值 | 单位 | 来源 |"
        )
    except StopIteration as exc:
        raise ValueError(f"{case_id} 缺少输入参数表") from exc
    end = start
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    table = "\n".join(lines[start:end])
    # 摘出结果表的关键行；详细逐路径/逐层中间结果留在完整附录。
    highlights = []
    i = end
    while i + 1 < len(lines):
        if lines[i].lstrip().startswith("|") and re.match(r"^\|[\s:|\-]+\|$", lines[i + 1].strip()):
            headers = [x.strip() for x in lines[i].strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                if i + 1 < len(lines) and re.match(r"^\|[\s:|\-]+\|$", lines[i + 1].strip()):
                    break
                rows.append([x.strip() for x in lines[i].strip().strip("|").split("|")])
                i += 1
            detailed = any(
                x in headers[0] for x in ("路径", "房间", "楼层", "管段", "气密性", "积尘")
            )
            if detailed and len(rows) > 2:
                rows = [rows[0], rows[-1]]
            for row in rows:
                if len(row) == len(headers):
                    highlights.append(
                        "；".join(f"{h} {v}" for h, v in zip(headers, row, strict=True)) + "。"
                    )
            continue
        i += 1
    core = []
    clauses = []
    on_clause = False
    skip_detail = False
    for line in lines[end:]:
        text = line.strip()
        if text.startswith("|"):
            continue
        if re.match(r"\*\*第[一二三四五六七八九十]+步", text):
            on_clause = "条文" in text
            continue
        if "条文判定：" in text or "本例不涉及条文判定" in text:
            if "不涉及条文" not in text:
                clauses.append(text.replace("条文判定：", ""))
            continue
        if text in ("各路径代入：", "各管段计算结果：", "逐层计算结果："):
            skip_detail = True
            continue
        if skip_detail and (text.startswith(("- 卧室", "$Q_B", "甲醛散发量"))):
            continue
        if skip_detail and not text:
            skip_detail = False
            continue
        if on_clause and text.startswith("- "):
            clauses.append(text)
            continue
        if ("满足" in text or "不满足" in text) and re.search(r"GB/T|JGJ/T|GB |标准|条文", text):
            clauses.append(text)
            continue
        if on_clause and not text:
            on_clause = False
            continue
        if text.startswith("### "):
            continue
        core.append(line)
    # 正文只保留首个房间或路径作为代入示例，其余完整明细留在附录。
    filtered = []
    seen = set()
    discard_continuation = False
    for line in core:
        match = re.match(r"^-\s*(卧室|路径)\s*\d+\s*[：:]", line.strip())
        if match:
            kind = match.group(1)
            discard_continuation = kind in seen
            seen.add(kind)
            if discard_continuation:
                continue
        elif discard_continuation:
            if line.startswith("  ") or not line.strip():
                continue
            discard_continuation = False
        filtered.append(line)
    core = filtered
    calc = "\n".join(core).strip()
    # 保存原有计算主线，结果摘要只引用原演算中明确的结果语句。
    candidates = [
        x.strip()
        for x in core
        if x.strip()
        and re.search(r"结果|设计风量|风机风量|全户设计|工作点|中和面", x)
        and re.search(r"\d", x)
    ]
    if not candidates:
        candidates = [
            x.strip() for x in core if re.search(r"\d", x) and not x.strip().startswith("$$")
        ][-1:]
    summary = "\n\n".join(candidates[-3:]) if candidates else "计算所得各项结果见完整演算附录。"
    if highlights:
        summary = "\n\n".join(highlights)
    if case_id == "ex5-07":
        threshold = next(iter(result["scenarios"].values()))["opening"]["threshold_pa"]
        calc = (
            f"采用多区稳态质量平衡；围护缝隙按幂律、室内门缝和自然补风口按孔口计算。油烟机及新风按理想定风量，{threshold:g} Pa 为示例提示阈值，不是燃气安全合格限值。\n\n"
            r"$$\sum_j \dot m_{ij}=0,\quad Q=C|\Delta p|^n,\quad C=(n_{50}V/3600)/50^n$$"
        )
        if inputs:
            volume = float(inputs["volume_m3"])
            coeffs = "、".join(
                f"n₅₀={n:g} h⁻¹ 时 {float(n) * volume / 3600 / 50**0.65:.7g}"
                for n in inputs["n50_per_h"]
            )
            calc += f"\n\n代入 V={volume:g} m³、n=0.65：总缝隙系数为 {coeffs} m³/(s·Pa⁰·⁶⁵)，按房间均分。"
        calc += "\n\n**敏感性说明：** 比较两档气密性及补风位置，其他条件保持不变。"
        ns = list(result["scenarios"])
        main = [
            "| 方案 | " + " | ".join(f"n₅₀={n} h⁻¹" for n in ns) + " |",
            "|---|" + "---:|" * len(ns),
        ]
        counter = [
            "| 反例 | " + " | ".join(f"n₅₀={n} h⁻¹" for n in ns) + " |",
            "|---|" + "---:|" * len(ns),
        ]
        labels = {
            "no_makeup": "无补风",
            "interlock": "新风联锁",
            "opening_kitchen": "厨房自然补风",
            "mechanical_kitchen": "厨房机械补风",
        }
        for key, label in labels.items():
            values = []
            for n in ns:
                val = result["scenarios"][n][key]
                values.append(f"{val['pressures_pa'][val['gas_zone']]:.3f} Pa")
            main.append("| " + label + " | " + " | ".join(values) + " |")
        if "minimum_makeup" in result:
            main.append(
                "| 所需最小机械补风量 | "
                + " | ".join(
                    f"{result['minimum_makeup'][n]['mechanical']['value'] * 3600:.2f} m³/h"
                    for n in ns
                )
                + " |"
            )
            main.append(
                "| 所需最小自然补风口面积 | "
                + " | ".join(
                    f"{result['minimum_makeup'][n]['opening']['value'] * 10000:.2f} cm²" for n in ns
                )
                + " |"
            )
        counter.append(
            "| 起居室自然补风口 | "
            + " | ".join(
                f"{result['scenarios'][n]['opening']['pressures_pa'][result['scenarios'][n]['opening']['gas_zone']]:.3f} Pa"
                for n in ns
            )
            + " |"
        )
        summary = (
            "主方案（厨房相对室外压力）：\n\n"
            + "\n".join(main)
            + "\n\n反例：补风口不在厨房（厨房相对室外压力）。\n\n"
            + "\n".join(counter)
            + f"\n\n提示阈值为 {threshold:g} Pa；反算压力容差 0.01 Pa，机械补风与自然开口分别单独计算，不叠加。厨房机械补风方案应核实实际设备能力，不能以计算替代现场安全验证。"
        )
    if "design" in result and "fan" in result and isinstance(result["design"], (int, float)):
        summary = f"全户设计风量 {result['design'] * 3600:.4g} m³/h，风机风量 {result['fan'] * 3600:.4g} m³/h。"
    return (
        "\n\n".join(
            [
                "**已知条件**",
                f"根据{title}给定条件计算，输入参数如下。",
                table,
                "**计算**",
                calc or "按输入条件进行计算，详细过程见附录。",
                "**结果**",
                summary,
                "**条文对照**",
                "\n".join(clauses) if clauses else "本例不涉及条文对照。",
                "完整演算见附录 X。",
                f"本算例由 OpenResiVent v{__version__} 计算，算例文件 cases/book/{chapter}/{case_id}.yaml",
            ]
        )
        + "\n"
    )
