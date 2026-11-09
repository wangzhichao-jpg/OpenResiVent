"""检查前端构建产物的静态外部资源引用，不访问网络。"""

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

# 上游未修改文件的单条回退地址；路径、文件哈希和地址三项必须同时匹配。
UPSTREAM_CDN_ALLOWLIST = frozenset(
    {
        (
            "pyodide/pyodide.mjs",
            "04c052c815abb0bf2981fa38c2dfa58e3120ee5288c956df2b2a15e301782c5f",
            "https://cdn.jsdelivr.net/pyodide/v${d.version}/full/",
        ),
        (
            "pyodide/pyodide.js",
            "b4cb23a53aba19c221659b9fb40a2f18281d685691dc06647fb0afd0681baf98",
            "https://cdn.jsdelivr.net/pyodide/v${d.version}/full/",
        ),
    }
)


class AssetParser(HTMLParser):
    """收集 HTML 资源属性。"""

    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("src", "href") and value:
                self.references.append(value)


def external(value: str) -> bool:
    """判断 URL 是否请求非本机主机；data/blob/相对路径不请求外网。"""
    value = value.strip().strip("\"'")
    if value.startswith(("data:", "blob:", "node:", "#")):
        return False
    parsed = urlsplit(value)
    if value.startswith("//") or parsed.scheme in ("http", "https"):
        return parsed.hostname not in ("localhost", "127.0.0.1", "::1")
    return bool(parsed.scheme)


def allowed_upstream_references(root: Path) -> list[tuple[str, str, str]]:
    """返回实际存在且路径、内容哈希和回退地址均匹配的上游引用。"""
    matches = []
    for relative, expected, url in sorted(UPSTREAM_CDN_ALLOWLIST):
        path = root / relative
        if not path.is_file() or path.is_symlink():
            continue
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            continue
        text = content.decode("utf8")
        refs = re.findall(r'\bsetCdnUrl\s*\(\s*["\'`]([^"\'`]+)', text)
        if url in refs:
            matches.append((relative, expected, url))
    return matches


def scan(root: Path) -> list[str]:
    """扫描 HTML、CSS 加载位置和 JS 字面量请求位置；动态表达式需 CSP 约束。"""
    bad = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in (".html", ".js", ".mjs", ".cjs", ".css"):
            continue
        text = path.read_text(encoding="utf8")
        refs = []
        if path.suffix == ".html":
            parser = AssetParser()
            parser.feed(text)
            refs += parser.references
        elif path.suffix == ".css":
            refs += [
                a or b
                for a, b in re.findall(
                    r'url\(\s*["\']([^"\']+)["\']\s*\)|url\(\s*([^\s)]+)\s*\)', text, re.IGNORECASE
                )
            ]
            refs += re.findall(r'@import\s+["\']([^"\']+)', text, re.IGNORECASE)
        else:
            refs += re.findall(r'(?:\bfetch|\bimport|\bimportScripts)\s*\(\s*["\']([^"\']+)', text)
            # 有些运行时通过 setCdnUrl 保存回退地址，而不是直接在 fetch 中写字面量。
            refs += re.findall(r'\bsetCdnUrl\s*\(\s*["\'`]([^"\'`]+)', text)
            refs += re.findall(
                r'\.open\s*\(\s*["\'][A-Z]+["\']\s*,\s*["\']([^"\']+)', text, re.IGNORECASE
            )
            refs += re.findall(r'\bimport\s+(?:[^;]*?\s+from\s+)?["\']([^"\']+)["\']', text)
        relative = path.relative_to(root).as_posix()
        for value in refs:
            if not external(value):
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if (relative, digest, value) not in UPSTREAM_CDN_ALLOWLIST:
                bad.append(f"{relative}: {value}")
    return bad


if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1] if len(sys.argv) > 1 else "build/web")
    if not root.is_dir():
        raise SystemExit("构建目录不存在")
    errors = scan(root)
    if errors:
        raise SystemExit("\n".join(errors))
    allowed = allowed_upstream_references(root)
    print(f"未发现未授权静态外部资源引用；上游精确白名单命中 {len(allowed)} 项。")
    for relative, digest, url in allowed:
        print(f"白名单：{relative} SHA256={digest} 地址={url}")
    print("动态请求由同源约束、内容安全策略及禁网测试共同限制。")
