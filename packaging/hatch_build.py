"""构建 wheel 时仅打包本机服务前端，源码包不含构建输出。"""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """将构建好的静态页面加入 wheel 或源码包。"""

    def initialize(self, version, build_data):
        web = Path(self.root) / "build" / "web"
        if self.target_name != "wheel" or not (web / "index.html").is_file():
            return
        included = build_data.setdefault("force_include", {})
        for path in sorted(web.rglob("*")):
            relative = path.relative_to(web)
            if path.is_symlink():
                raise ValueError(f"前端构建目录不允许符号链接: {relative}")
            if (
                not path.is_file()
                or "pyodide" in str(relative).lower()
                or path.suffix.lower() in {".wasm", ".whl", ".zip"}
            ):
                continue
            included[str(path)] = f"openresivent/web/{relative.as_posix()}"
