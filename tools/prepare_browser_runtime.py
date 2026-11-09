"""准备本机 Pyodide 运行时和软件源码，校验锁文件 SHA256；不部署。"""

import argparse
import hashlib
import http.client
import json
import os
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NPM = ROOT / "web/node_modules/pyodide"
OUT = ROOT / "build/browser-runtime"
DEFAULT_MIRROR = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/"
PACKAGES = ("numpy", "scipy", "pydantic", "pyyaml")
CORE_SHA256 = {
    "pyodide-lock.json": "9c45b916001a750f4102fc287494f3eab215909c7535c626a20db80fd6333e2c",
    "pyodide.asm.wasm": "a50dd1843f805a0b7c45b61037ee0d7b26dfe85efe0e18ef95a34ad24e401f5f",
    "python_stdlib.zip": "16611534726e5d8ac2bd8f926410b2dcb8d6f49aa24913463533b457a2115c16",
    "pyodide.asm.js": "6b4c90de5b7172873f04f21884d0e9d2274e305fe32116558fe3e4fbe3618d51",
    "pyodide.js": "b4cb23a53aba19c221659b9fb40a2f18281d685691dc06647fb0afd0681baf98",
    "pyodide.mjs": "04c052c815abb0bf2981fa38c2dfa58e3120ee5288c956df2b2a15e301782c5f",
}


def sha256(path: Path) -> str:
    """按文件字节计算 SHA256。"""
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def required_packages(lock: dict) -> list[str]:
    """返回所需包及传递依赖；只接受锁文件已有的名字。"""
    result = set()

    def visit(name):
        name = name.lower().replace("_", "-")
        if name in result:
            return
        if name not in lock["packages"]:
            raise ValueError(f"锁文件缺少依赖 {name}")
        result.add(name)
        for dependency in lock["packages"][name]["depends"]:
            visit(dependency)

    for name in PACKAGES:
        visit(name)
    return sorted(result)


def download(url: str, destination: Path, expected: str) -> None:
    """经 TLS 下载并验证预期 SHA256，失败不保留损坏文件。"""
    if destination.is_file() and sha256(destination) == expected:
        return
    temp = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "OpenResiVent-browser-runtime/1"}
            )
            with urllib.request.urlopen(request, timeout=90) as response, temp.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            actual = sha256(temp)
            if actual != expected:
                raise ValueError(f"SHA256 不符：{destination.name}，实际 {actual}")
            temp.replace(destination)
            return
        except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError) as exc:
            temp.unlink(missing_ok=True)
            if attempt == 2:
                raise
            delay = 2**attempt
            print(f"下载或校验失败（第 {attempt + 1} 次）：{exc}；{delay} 秒后重试", flush=True)
            time.sleep(delay)
        finally:
            temp.unlink(missing_ok=True)


def write_source_archive(root: Path, archive_path: Path) -> None:
    """源码归档固定时间戳和权限，保证不同检出时间的构建一致。"""
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for base_path in (root / "src/openresivent", root / "data"):
            for path in sorted(base_path.rglob("*")):
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or "__pycache__" in path.parts
                    or "private" in path.parts
                    or path.suffix not in (".py", ".yaml")
                    or "contamx" in path.name.lower()
                ):
                    continue
                info = zipfile.ZipInfo(path.relative_to(root).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description="准备本机浏览器计算运行时。")
    parser.add_argument("--dry-run", action="store_true", help="只列出计划，不下载、不写入")
    args = parser.parse_args()
    if not (NPM / "pyodide-lock.json").is_file():
        if args.dry_run:
            print("尚未安装前端依赖；计划先执行 npm ci，之后准备运行时；仅预览，不下载、不写入。")
            return
        raise SystemExit("请先在 web 目录执行 npm ci")
    lock = json.loads((NPM / "pyodide-lock.json").read_text())
    if lock["info"]["version"] != "0.27.7":
        raise ValueError("Pyodide 版本与已审查版本不一致")
    base = os.environ.get("ORV_PYODIDE_MIRROR", DEFAULT_MIRROR).rstrip("/") + "/"
    if not base.startswith("https://"):
        raise ValueError("下载源必须使用 HTTPS")
    if args.dry_run:
        for name in required_packages(lock):
            package = lock["packages"][name]
            print(
                f"计划获取 {name} {package['version']}: {base}{package['file_name']} SHA256={package['sha256']}"
            )
        print(f"计划生成 {OUT}；仅预览，不下载、不写入。")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for name in (
        "pyodide.js",
        "pyodide.mjs",
        "pyodide.asm.js",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
        "pyodide-lock.json",
    ):
        if sha256(NPM / name) != CORE_SHA256[name]:
            raise ValueError(f"运行时 SHA256 不符：{name}")
        shutil.copy2(NPM / name, OUT / name)
    hashes = {}
    for name in required_packages(lock):
        package = lock["packages"][name]
        filename = package["file_name"]
        print(f"获取 {name} {package['version']}: {base}{filename}", flush=True)
        download(base + filename, OUT / filename, package["sha256"])
        hashes[filename] = package["sha256"]
    # 复制许可证全文用于本地构建包，MPL 文件本身保持原样。
    licenses = OUT / "licenses"
    licenses.mkdir(exist_ok=True)
    for license_path in (ROOT / "web/licenses").glob("*.txt"):
        shutil.copy2(license_path, licenses / license_path.name)
    for filename in hashes:
        with zipfile.ZipFile(OUT / filename) as archive:
            for item in archive.namelist():
                leaf = item.rsplit("/", 1)[-1].lower()
                if leaf.startswith(
                    ("license", "licence", "copying", "notice")
                ) and not item.endswith("/"):
                    target = licenses / filename / item
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(item))
    # 源码和公开数据置于同一归档：无项目外原文、私有规则或第三方二进制。
    archive_path = OUT / "openresivent.zip"
    write_source_archive(ROOT, archive_path)
    for name in (
        "pyodide.js",
        "pyodide.mjs",
        "pyodide.asm.js",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
        "pyodide-lock.json",
        "openresivent.zip",
    ):
        hashes[name] = sha256(OUT / name)
    for path in sorted(licenses.rglob("*")):
        if path.is_file():
            hashes[path.relative_to(OUT).as_posix()] = sha256(path)
    (OUT / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")
    print(
        "文件数",
        len(hashes),
        "总字节",
        sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()),
        flush=True,
    )


if __name__ == "__main__":
    main()
