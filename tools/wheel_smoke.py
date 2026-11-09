"""在源码目录之外对已安装 wheel 执行七项本机冒烟。"""

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from openresivent import __version__

ROOT = Path(__file__).resolve().parents[1]


def wait_http(url, process):
    """等待本机服务并返回正文与响应头。"""
    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError("服务提前退出")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.read(), response.headers
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    raise TimeoutError("本机服务未启动")


def main():
    """使用独立虚拟环境命令；不从源码目录导入包。"""
    envdir = ROOT / "build/p310/wheel-env"
    binary = envdir / "bin/resivent"
    python = envdir / "bin/python"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("ORV_WEB_DIR", None)
    env["BROWSER"] = "/bin/true"
    with tempfile.TemporaryDirectory(prefix="orv-wheel-smoke-") as tmp:
        tmp = Path(tmp)
        source = ROOT / "cases/book/ch02/ex2-01.yaml"
        shutil.copy2(source, tmp / "case.yaml")
        base = yaml.safe_load((ROOT / "cases/studies/makeup_base.yaml").read_text())
        spec = yaml.safe_load((ROOT / "cases/studies/makeup_sweep.yaml").read_text())
        spec["factors"] = {
            k: {"values": v["values"][:2] if i == 0 else v["values"][:1]}
            for i, (k, v) in enumerate(spec["factors"].items())
        }
        (tmp / "makeup_base.yaml").write_text(yaml.safe_dump(base, allow_unicode=True))
        (tmp / "scan.yaml").write_text(yaml.safe_dump(spec, allow_unicode=True))
        package = subprocess.check_output(
            [str(python), "-c", "import openresivent; print(openresivent.__file__)"],
            cwd=tmp,
            env=env,
            text=True,
        ).strip()
        if str(envdir) not in package:
            raise RuntimeError("未从独立 wheel 环境加载")
        version = subprocess.check_output(
            [str(binary), "--version"], cwd=tmp, env=env, text=True
        ).strip()
        if version != __version__:
            raise RuntimeError("版本不符")
        subprocess.run(
            [str(binary), "run", str(tmp / "case.yaml"), "--out", str(tmp / "run")],
            cwd=tmp,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                str(binary),
                "check",
                str(ROOT / "cases/workflows/household_example.yaml"),
                "--out",
                str(tmp / "check"),
            ],
            cwd=tmp,
            env=env,
            check=True,
        )
        check = json.loads((tmp / "check/result.json").read_text())
        if (
            abs(check["ventilation"]["design"] * 3600 - 194.0) > 1e-9
            or not (tmp / "check/report.docx").is_file()
        ):
            raise RuntimeError("一户校核结果或报告异常")
        value = json.loads((tmp / "run/ex2-01.json").read_text())["flow_m3_s"] * 3600
        if abs(value - 90) > 1e-10:
            raise RuntimeError("算例结果不符")
        subprocess.run(
            [
                str(binary),
                "sweep",
                str(tmp / "scan.yaml"),
                "--out",
                str(tmp / "sweep"),
                "--workers",
                "1",
            ],
            cwd=tmp,
            env=env,
            check=True,
        )
        if not (tmp / "sweep/results.xlsx").is_file():
            raise RuntimeError("扫描输出缺失")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        process = subprocess.Popen(
            [str(binary), "serve", "--port", str(port)],
            cwd=tmp,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            page, headers = wait_http(f"http://127.0.0.1:{port}/", process)
            if b'id="app"' not in page or "default-src 'self'" not in headers.get(
                "Content-Security-Policy", ""
            ):
                raise RuntimeError("页面或 CSP 异常")
            match = re.search(rb'<script[^>]+src="([^"]+)"', page)
            if not match:
                raise RuntimeError("前端脚本缺失")
            script, _ = wait_http(f"http://127.0.0.1:{port}" + match.group(1).decode(), process)
            help_page, _ = wait_http(f"http://127.0.0.1:{port}/browser-runtime-help", process)
            if (
                "浏览器运行时需单独准备".encode() not in script
                or "浏览器运行时需单独准备".encode() not in help_page
            ):
                raise RuntimeError("浏览器模式提示或准备说明缺失")
        finally:
            process.terminate()
            process.wait(timeout=15)
        log = tmp / "desktop.log"
        with log.open("w") as stream:
            process = subprocess.Popen(
                [str(binary), "desktop"], cwd=tmp, env=env, stdout=stream, stderr=stream
            )
            try:
                for _ in range(200):
                    match = re.search(r"http://127\.0\.0\.1:\d+/", log.read_text())
                    if match:
                        break
                    if process.poll() is not None:
                        raise RuntimeError("桌面入口提前退出")
                    time.sleep(0.1)
                else:
                    raise TimeoutError("桌面回退未启动")
                page, headers = wait_http(match.group(), process)
                if b'id="app"' not in page or "default-src 'self'" not in headers.get(
                    "Content-Security-Policy", ""
                ):
                    raise RuntimeError("桌面页面或 CSP 异常")
            finally:
                process.terminate()
                process.wait(timeout=15)
    print("wheel 环境：", package)
    print(
        "版本、run、check、serve、sweep、desktop、浏览器模式提示七项通过；示例风量", value, "m³/h。"
    )


if __name__ == "__main__":
    main()
