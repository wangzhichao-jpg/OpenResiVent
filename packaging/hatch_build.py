"""构建时可选打包本地前端；未构建时不引入外部资源。"""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """将构建好的静态页面加入 wheel 或源码包。"""

    def initialize(self, version, build_data):
        web = Path(self.root) / "build" / "web"
        if (web / "index.html").is_file():
            target = "openresivent/web" if self.target_name == "wheel" else "build/web"
            build_data.setdefault("force_include", {})[str(web)] = target
