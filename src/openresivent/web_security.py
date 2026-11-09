"""检查前端构建产物的静态外部资源引用，不访问网络。"""

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


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
    if value.startswith(("data:", "blob:", "#")):
        return False
    parsed = urlsplit(value)
    if value.startswith("//") or parsed.scheme in ("http", "https"):
        return parsed.hostname not in ("localhost", "127.0.0.1", "::1")
    return bool(parsed.scheme)


def scan(root: Path) -> list[str]:
    """扫描 HTML、CSS 加载位置和 JS 字面量请求位置；动态表达式需 CSP 约束。"""
    bad = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in (".html", ".js", ".css"):
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
            refs += re.findall(
                r'\.open\s*\(\s*["\'][A-Z]+["\']\s*,\s*["\']([^"\']+)', text, re.IGNORECASE
            )
            refs += re.findall(r'\bimport\s+(?:[^;]*?\s+from\s+)?["\']([^"\']+)["\']', text)
        bad.extend(f"{path.relative_to(root)}: {x}" for x in refs if external(x))
    return bad


if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1] if len(sys.argv) > 1 else "build/web")
    if not root.is_dir():
        raise SystemExit("构建目录不存在")
    errors = scan(root)
    if errors:
        raise SystemExit("\n".join(errors))
    print("未发现静态外部资源请求引用；动态请求由内容安全策略限制。")
