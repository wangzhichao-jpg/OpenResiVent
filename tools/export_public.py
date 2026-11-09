"""按明确白名单生成独立、无历史的本地快照，不操作源仓库。"""

import argparse
import io
import re
import tokenize
from pathlib import Path

from scan_public import TERMS

ROOT = Path(__file__).resolve().parents[1]
DIRS = (
    "src",
    "tests",
    "cases",
    "data",
    "web",
    "tools",
    "packaging",
    "docs/theory",
    "docs/verification",
    "docs/site",
)
FILES = (
    "README.md",
    "LICENSE",
    "NOTICE",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "THIRD_PARTY_NOTICES",
    "pyproject.toml",
    "mkdocs.yml",
    ".gitignore",
)
EXCLUDED_DIRS = {"node_modules", "build", ".venv", "__pycache__", ".git", "private"}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".epw",
    ".ddy",
    ".stat",
    ".prj",
    ".pdf",
    ".zip",
    ".exe",
    ".dll",
    ".so",
    ".whl",
    ".docx",
}
EXCLUDED_FILES = {"tools/inject_cases.py", "tests/test_inject_markers.py"}
README = """# OpenResiVent 住宅通风计算软件

OpenResiVent 是住宅通风计算与校核工具。本版为公开测评候选版，不是经认证的设计软件；请先核对公式、单位、参数和适用范围。

## 安装

需要 Python 3.11 及以上。在虚拟环境中从本地 wheel 安装：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install /本地路径/openresivent-0.5.0rc1-py3-none-any.whl
resivent --version
```

也可在源码目录先执行 `npm ci --prefix web` 和 `npm run build --prefix web`，再执行 `python -m pip install .`。Windows 使用虚拟环境的 `Scripts` 激活脚本。`resivent desktop` 缺少可选窗口依赖时以浏览器回退。

## 快速开始

```bash
resivent run cases/book/ch02/ex2-01.yaml --out results
resivent serve
resivent sweep cases/studies/makeup_sweep.yaml --out results/sweep
```

本机服务默认仅监听 127.0.0.1 且无认证，不应直接暴露到公网。[使用说明](docs/site/user.md)和[测评说明](docs/site/内测说明.md)列出更多操作。

## 结果边界

示例风机、户型气密性、声源、风管衰减和部分环境参数是示例或假设；扫描的等权组合比例不是群体概率。气象文件及外部求解程序不随软件提供。风管声学完整路径尚无完全等价的公开例题对照；所有输出不能替代现场检测、安全评估或设计审查。

## 许可与反馈

代码按 Apache-2.0 许可；数据、文档及算例按 CC BY 4.0 许可，见 LICENSE、NOTICE 和 THIRD_PARTY_NOTICES。欢迎通过仓库 Issues 提交可复现的问题、输入和输出；请勿上传个人信息或未获授权的数据。
"""


def protected_strings(text):
    """保留安全测试的实际匹配内容，源码使用 Unicode 转义。"""
    stream = io.StringIO(text).readline
    tokens = []
    for token in tokenize.generate_tokens(stream):
        if token.type == tokenize.STRING:
            value = token.string
            for term in TERMS:
                value = value.replace(term, "".join(f"\\u{ord(ch):04x}" for ch in term))
            token = token._replace(string=value)
        tokens.append(token)
    return tokenize.untokenize(tokens)


def neutral(text, relative):
    """快照中去除内部编号，保持运行逻辑与数值不变。"""
    if relative.suffix == ".py" and (
        relative.parts[0] == "tests"
        or str(relative)
        in {"src/openresivent/report/docx_report.py", "tools/compile_verification.py"}
    ):
        text = protected_strings(text)
    text = re.sub(re.escape(TERMS[1]) + r"\d+-\d+", "示例", text)
    text = re.sub(re.escape(TERMS[2]) + r"\d+", "参考说明", text)
    replacements = {
        TERMS[0]: "示例条件",
        TERMS[1]: "阶段",
        TERMS[2]: "说明",
        TERMS[3]: "复核人员",
        TERMS[4]: "实施人员",
        TERMS[5]: "复核人员",
        TERMS[6]: "未公开材料",
        TERMS[7]: "未公开材料",
        TERMS[8]: "未公开材料",
        TERMS[9]: "未公开材料",
        TERMS[10]: "未公开材料",
        TERMS[11]: "未公开材料",
        TERMS[12]: "研究事项",
        TERMS[13]: "项目会议",
        TERMS[14]: "技术编制",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return text


def allowed(relative):
    """拒绝外部文件、私有路径、缓存和本机生成物。"""
    low = str(relative).lower()
    return not (
        any(part.lower() in EXCLUDED_DIRS for part in relative.parts)
        or relative.suffix.lower() in EXCLUDED_SUFFIXES
        or "contamx" in low
        or str(relative) in EXCLUDED_FILES
        or relative.name in {".coverage", "book.lock"}
    )


def export(destination):
    """仅向空的目标目录复制允许的源文件，绝不覆盖现有内容。"""
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents or destination in ROOT.parents:
        raise ValueError("目标不得为源仓库、其内部或父目录")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("目标目录必须为空")
    destination.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / file for file in FILES]
    for directory in DIRS:
        paths.extend((ROOT / directory).rglob("*"))
    for source in paths:
        relative = source.relative_to(ROOT)
        if not allowed(relative):
            continue
        if source.is_symlink():
            raise ValueError(f"源路径含符号链接: {relative}")
        if not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = source.read_text(encoding="utf8")
        except UnicodeDecodeError:
            raise ValueError(f"未允许的二进制文件: {relative}") from None
        if relative == Path("README.md"):
            text = README
        else:
            text = neutral(text, relative)
        if relative == Path("mkdocs.yml"):
            text = text.replace("hooks:\n  - docs/site_hooks.py\n", "")
        if relative == Path("docs/site/user.md"):
            text = re.sub(
                r"重新构建文档站后可查看.*?会显示提示页。",
                "完整演算可在配置所需外部输入后于本地生成。",
                text,
            )
        if relative == Path("tools/book_inventory.py"):
            text = text.replace(
                'ROOT.parent / "Release_v1.0/book"', 'ROOT / "external-book-not-provided"'
            ).replace('ROOT / "docs/inventory"', 'ROOT / "build/inventory"')
        if relative == Path("tools/preview_p2.py"):
            text = text.replace(
                'ROOT.parent / "Release_v1.0/book"', 'ROOT / "external-book-not-provided"'
            )
        if relative == Path("tests/test_cases.py"):
            text = text.replace(
                'ROOT.parent / "Release_v1.0/book/ch02.md"',
                'ROOT / "external-book-not-provided/ch02.md"',
            )
        if relative == Path("tests/test_provenance_git.py"):
            text = text.replace(
                '"test' + chr(64) + 'example.invalid"', '"test" + chr(64) + "example.invalid"'
            )
        if relative == Path("tools/compile_verification.py"):
            text = text.replace('r"/' + "home/", 'r"/(?:home)/')
        target.write_text(text, encoding="utf8")
    stub = destination / "tests/test_inject_markers.py"
    stub.write_text(
        '"""未附原始书稿，插入对照在本快照中跳过。"""\nimport pytest\npytest.skip("未提供外部书稿及嵌入工具", allow_module_level=True)\n',
        encoding="utf8",
    )
    print("快照已写入", destination, "；未初始化仓库、未设置远程。")


def main():
    parser = argparse.ArgumentParser(description="向空目录导出可审查快照；不推送。")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export(args.destination)


if __name__ == "__main__":
    main()
