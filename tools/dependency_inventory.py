"""汇总独立 wheel 环境、前端锁文件及本机桌面构建的依赖元数据。"""

import json
import re
import shutil
import subprocess
import sys
from importlib.metadata import distributions, packages_distributions
from pathlib import Path

from PyInstaller.archive.readers import ZlibArchiveReader

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/p310"


def license_name(d):
    """从发行包元数据提取许可证标识，不以推断代替未知值。"""
    m = d.metadata
    text = m.get("License-Expression") or m.get("License") or ""
    if len(text) > 120 or "\n" in text:
        text = "; ".join(
            c.split(" :: ")[-1] for c in m.get_all("Classifier", []) if c.startswith("License ::")
        )
    return text or "未声明，须核查"


def rows(table):
    """格式化名称、版本和许可证。"""
    return "\n".join(
        f"| {a} | {b} | {c.replace(chr(10), ' ').replace('|', '/')} |" for a, b, c in table
    )


def sanitize_sbom(value):
    """仅移除指向本机构建目录的文件 URL。"""
    if isinstance(value, dict):
        return {
            k: sanitize_sbom(v)
            for k, v in value.items()
            if not (k == "url" and isinstance(v, str) and v.startswith("file:"))
        }
    if isinstance(value, list):
        return [
            sanitize_sbom(v)
            for v in value
            if not (isinstance(v, dict) and str(v.get("url", "")).startswith("file:"))
        ]
    return value


def main():
    py = BUILD / "wheel-env/bin/python"
    code = """import json\nfrom importlib.metadata import distributions\nout=[]\nfor d in distributions():\n m=d.metadata; s=m.get('License-Expression') or m.get('License') or ''\n if len(s)>120 or '\\n' in s:s='; '.join(c.split(' :: ')[-1] for c in m.get_all('Classifier',[]) if c.startswith('License ::'))\n out.append([m['Name'],d.version,s or '未声明，须核查'])\nprint(json.dumps(out))"""
    runtime = sorted(
        json.loads(subprocess.check_output([str(py), "-c", code])), key=lambda x: x[0].lower()
    )
    lock = json.loads((ROOT / "web/package-lock.json").read_text())
    frontend = []
    for path, package in lock["packages"].items():
        if path and "node_modules/" in path:
            frontend.append(
                (
                    path.split("node_modules/")[-1],
                    package.get("version", "未知"),
                    package.get("license", "未声明，须核查"),
                )
            )
    archive = ZlibArchiveReader(str(ROOT / "build/desktop-build/resivent-desktop/PYZ-00.pyz"))
    modules = {x.split(".")[0] for x in archive.toc}
    internal = BUILD / "desktop-dist/resivent-desktop/_internal"
    modules |= {p.name.split(".")[0] for p in internal.iterdir() if p.is_dir()}
    mapping = packages_distributions()
    names = {name.lower() for module in modules for name in mapping.get(module, [])}
    desktop = sorted(
        (
            (d.metadata["Name"], d.version, license_name(d))
            for d in distributions()
            if d.metadata["Name"].lower() in names
        ),
        key=lambda x: x[0].lower(),
    )

    def pip_license_map(interpreter):
        raw = subprocess.check_output(
            [sys.executable, "-m", "piplicenses", "--python", str(interpreter), "--format=json"]
        )
        return {item["Name"].lower(): item["License"] for item in json.loads(raw)}

    runtime_licenses = pip_license_map(py)
    desktop_licenses = pip_license_map(sys.executable)
    runtime = [(n, v, runtime_licenses.get(n.lower(), lic)) for n, v, lic in runtime]
    desktop = [(n, v, desktop_licenses.get(n.lower(), lic)) for n, v, lic in desktop]
    notice = (
        """# 第三方依赖说明

本清单列出独立 wheel 安装环境、前端锁文件全部依赖（含开发及可选平台包）和当前 Linux 桌面打包分析，版本为本机候选构建的解析结果，并非未来安装时的锁定保证。完整许可证文本按依赖从已安装发行包和前端包收集于本机构建目录 `build/p310/third-party-licenses/`；分发任何二进制前须随对应产物附带这些文本并复核最终依赖。SBOM 分别为 `docs/site/sbom-python.json` 和 `docs/site/sbom-frontend.json`，前者对应 wheel 独立环境，后者仅前端运行依赖。前端表包含开发依赖，所以比运行 SBOM 范围更广。

项目以 Apache-2.0 许可代码。外部流场求解程序作为独立进程调用，不含在本程序或桌面包中；未发现无链接例外的 GPL/AGPL 组件作为 Python 或前端依赖被链接。此结论限本次清单与二进制检查，不等于对未来解析版本的保证。NumPy/SciPy 官方包可能包含 BSD 许可 OpenBLAS 与带 GCC Runtime Library Exception 的 libgfortran/libquadmath；它们是可替换的动态库，不能简单表述为“不含任何 GPL 文字”。桌面包中的系统 OpenSSL、Python 运行库、libstdc++ 等须按实际系统发行包附带许可；本机候选包未作为可分发发行件。

## Python wheel 安装环境（含传递依赖和 pip）

| 名称 | 版本 | 元数据许可 |
|---|---|---|
"""
        + rows(runtime)
        + """

## 前端锁文件（含运行、开发及可选依赖）

| 名称 | 版本 | 锁文件许可 |
|---|---|---|
"""
        + rows(frontend)
        + """

## Linux 桌面分析（PYZ 模块和打包目录映射）

以下是通过模块与发行包映射得到的保守清单，可能包含未执行的随包模块；系统动态库须另核。PyInstaller 引导程序使用带引导加载器例外的 GPL；本机打包器仅构建时使用。可选 pywebview 未装入此次候选包，桌面入口使用浏览器回退。

| 名称 | 版本 | 元数据许可 |
|---|---|---|
"""
        + rows(desktop)
        + "\n"
    )
    (ROOT / "THIRD_PARTY_NOTICES").write_text(notice, encoding="utf8")
    for kind in ("python", "frontend"):
        path = BUILD / f"sbom-{kind}.json"
        obj = sanitize_sbom(json.loads(path.read_text()))
        (ROOT / f"docs/site/sbom-{kind}.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
        )
    licenses = BUILD / "third-party-licenses"
    licenses.mkdir(exist_ok=True)
    # pip-licenses 输出包括已安装包实际许可全文；前端复制实际安装包中的许可文件。
    subprocess.run(
        [
            sys.executable,
            "-m",
            "piplicenses",
            "--python",
            str(py),
            "--with-license-file",
            "--format=json",
            "--output-file",
            str(licenses / "python-licenses.json"),
        ],
        check=True,
    )
    copied = 0
    for path, package in lock["packages"].items():
        if not path.startswith("node_modules/"):
            continue
        folder = ROOT / "web" / path
        if not folder.is_dir():
            continue
        target = licenses / "npm" / re.sub(r"[^A-Za-z0-9._-]", "_", path)
        for file in folder.iterdir():
            if file.is_file() and re.match(
                r"^(licen[sc]e|copying|notice)(\.|$)", file.name, re.IGNORECASE
            ):
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target / file.name)
                copied += 1
    print(
        "Python",
        len(runtime),
        "前端锁",
        len(frontend),
        "桌面模块",
        len(desktop),
        "前端许可文件",
        copied,
    )
    print(
        "未知前端许可",
        sum("未声明" in r[2] for r in frontend),
        "未知桌面许可",
        sum("未声明" in r[2] for r in desktop),
    )


if __name__ == "__main__":
    main()
