"""汇编验证文档为 Markdown 与 DOCX，不改变基准数字。"""

import re
from pathlib import Path

from docx import Document

from openresivent import __version__

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/p310"

SUMMARY = """# OpenResiVent 验证报告

版本：{version}。本报告汇编全部验证文档，并列出尚未完成的对照；通过仅表示所列工况满足所列判据，不表示整个模型或实际工程通过认证。资料内部编号和机构称谓在本汇编中省略；可重复性所需数据、数值与文献题名保留。缺数据时优先采用公开数值、标注精度的读图或明确假设，未用实测值填补缺口。

## 目录

- 各模块基准汇总及尚未完成事项
- 三维流动与空气龄
- 多区域网络对照
- 竖井、热回收与能耗趋势
- 风管声学、气象来源和参数扫描研究
- 下文逐篇汇编全部验证文档

## 各模块基准汇总及尚未完成事项

| 模块 | 基准与计算偏差 | 容差或判据 | 结论与范围 |
|---|---|---|---|
| M0 物性 | 公开饱和压力参考点；逐点测试 | 相对误差 0.1% | 通过；限测试温度点 |
| M1 新风量 | 示范二氧化碳算例 90 m³/h，数值差小于 10⁻¹⁰ m³/h | 绝对误差 10⁻¹⁰ m³/h | 通过；仅该算例 |
| M2 多区 | 非等温孔口最大差 0.02337%；污染物时间序列最大差 1.610% | 流量 1%，浓度 2% | 通过；仅所列元件、参数与时间序列 |
| M3 竖井 | 六层圆管网络 21 路径最大差 0.00274% | 1% | 通过；不代表矩形截面、非等温或现场验证 |
| M4 热回收 | 动态阻力翻倍风量剩余 81.49%，文献约 85%，差 −3.51 个百分点 | 无统一预设定量容差 | 趋势一致；定量复现未完成，需原始气象和滤网数据 |
| M5 能耗 | 四城市负荷降幅 30.37%～35.86%；参照 39.2%～52.3% | 无统一预设定量容差 | 趋势一致；未定量复现，需原始曲线、气象及运行数据 |
| M6 声学 | 手册第35页房间声压 28.977 dB，对照 29 dB，差 −0.023 dB | 0.5 dB | 通过 Thompson 例题；不代表经典模型或完整路径实验验证 |
| M7 户内补风 | 反算后前向代回 −15 Pa | 绝对误差 0.01 Pa | 通过所列假设工况；15 Pa 是示例提示值，不是安全限值 |
| M8 自然通风 | 双开口算例 0.303185 m³/s | 相对误差 10⁻⁵ | 通过；仅简化解析条件 |
| M9 风口 | 射流与布置判断及无效输入回归 | 条件布尔结果 | 通过所列条件；不代表真实产品实测 |
| M10 健康风险 | 慢性日摄入和风险的乘除法解析对照 | 浮点近似、边界条件 | 通过测试样例；输入参数存在假设 |
| M11 测试验收 | 设计 200、实测 185 m³/h，偏差 −7.5% | 浮点近似与逻辑断言 | 通过测试样例；不代替现场检测 |
| M12 产品检测 | 显热交换效率 93.75%，量纲与代入计算一致 | 浮点近似 | 通过假设算例；不代表设备实测 |
| C1 空气龄 | 活塞流出口 6.000000 s，对照 6 s | 相对差 <0.01% | 通过该标量方程示例；房间场非现场验证 |

尚待资料：滤网周期约 97 天的来源、两张结霜图的差异、热回收标准原文适用条件、典型气象再分发许可、有效换气率定义与实测数据；需独立核验，现有假设和读图不可冒充实测。风管声学完整路径尚无完全同条件公开对照。所有研究扫描的等权组合比例不是建筑群体概率。
"""


def neutral(text):
    """删除内部编号、组织及品牌称谓，不改动参考值。"""
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
    text = re.sub(r"https?://[^\s）`]+", "（资料链接见原参考条目）", text)
    from openresivent.core.private_terms import load_private_terms

    for term in load_private_terms():
        text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR\d+\b", "此前", text)
    for old, new in [
        ("NIST", "公开技术资料"),
        ("NOAA", "公开气象资料"),
        ("ASHRAE", "公开暖通"),
        ("Engineering ToolBox", "公开室内声传播资料"),
        ("CED Engineering", "公开"),
        ("nexoradesign.net", "公开声学资料"),
        ("按 D9", "按数据缺口处理原则"),
    ]:
        text = text.replace(old, new)
    text = re.sub(r"/(?:home)/[^\s`]+", "本机目录", text)
    return text


def render_docx(markdown, target):
    """将标题、段落、表格写入可编辑 DOCX。"""
    doc = Document()
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c or "") for c in row):
                    rows.append(row)
                i += 1
            if rows:
                width = max(map(len, rows))
                table = doc.add_table(rows=0, cols=width)
                table.style = "Table Grid"
                for row in rows:
                    cells = table.add_row().cells
                    for n, cell in enumerate(row):
                        cells[n].text = re.sub(r"[`*]", "", cell)
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading:
            doc.add_heading(re.sub(r"[`*]", "", heading[2]), level=min(len(heading[1]), 4))
        else:
            doc.add_paragraph(re.sub(r"[`*]", "", line))
        i += 1
    doc.save(target)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = sorted((ROOT / "docs/verification").glob("*.md"))
    text = SUMMARY.replace("{version}", __version__) + "\n## 文档汇编\n"
    for path in sources:
        text += "\n### " + path.stem + "\n\n" + path.read_text(encoding="utf8") + "\n"
    text = neutral(text)
    (OUT / "验证报告.md").write_text(text, encoding="utf8")
    render_docx(text, OUT / "验证报告.docx")
    print(f"汇编 {len(sources)} 个文档，输出 {OUT}/验证报告.md 和 .docx")


if __name__ == "__main__":
    main()
