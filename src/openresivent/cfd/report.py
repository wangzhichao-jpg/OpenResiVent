"""CFD 两种送排风布置的中文书稿片段。"""


def render(result: dict) -> str:
    """读取的 CFD 指标 → 可复核 Markdown。"""
    lines = [
        "| 参数 | 符号 | 数值 | 单位 | 来源 |",
        "|---|---|---:|---|---|",
        "| 房间尺寸 | $L×W×H$ | 4×3×2.5 | m | 示例值，需作者确认 |",
        "| 送风量 | $Q$ | 180 | m³/h | 示例值，需作者确认 |",
        "",
        "**第一步：计算。**",
        r"$$\tau_n=V/Q,\quad \eta_a=\tau_n/(2\bar\tau)$$",
        "| 布置 | 全室平均空气龄 s | 呼吸区平均空气龄 s | 换气效率 |",
        "|---|---:|---:|---:|",
    ]
    for k, label in [("upper", "上送上排"), ("lower", "上送下排")]:
        x = result[k]
        lines.append(
            f"| {label} | {x['average_age_s']:.2f} | {x['breathing_age_s']:.2f} | {x['air_change_efficiency'] * 100:.2f}% |"
        )
    lines += [
        f"质量守恒相对误差：上送上排 {result['upper'].get('mass_balance_relative', 0):.3g}，上送下排 {result['lower'].get('mass_balance_relative', 0):.3g}。",
        "书稿表6.1-1给出上送上排通常低于50%、上送下排约50%；本算例仅用于比较趋势，结果取决于风口、流量、扩散系数与边界。",
        "空气龄采用稳态被动标量，均匀有效扩散系数为假设，未考虑热浮力；并非现场验证。",
        "**敏感性说明：** 两种风口布置与三网格收敛分析体现几何和数值敏感性。",
        "本例不涉及条文判定。",
    ]
    return "\n".join(lines) + "\n"
