# 桌面版构建与运行

安装包内界面之后执行 `resivent desktop`。程序绑定 `127.0.0.1` 的随机空闲端口；安装可选依赖 `openresivent[desktop]`（pywebview，BSD-3-Clause）时优先打开窗口，否则用系统默认浏览器。浏览器模式保持服务运行，终端按 Ctrl+C 结束。桌面应用无认证，不应暴露到网络。Linux 图形环境、默认浏览器或 pywebview 运行库须由使用者配置。

## Linux 本地冒烟构建

本项目只构建 onedir 测试目录，不生成或发布安装包。先在源码目录按快速开始构建 `build/web`，然后在 systemd 用户任务及锁内安装 `.[bundle]`（PyInstaller，GPL-2.0-or-later，包含对打包应用的例外；构建工具不作为程序库链接）并执行 `python packaging/build_desktop.py`。依赖下载优先清华源，npm 优先 npmmirror，保留 TLS。测试目录默认 `build/desktop-dist/resivent-desktop/`；其可执行文件提供 `serve` 和 `desktop`。构建脚本自动检查私有规则、书稿、气象及 ContamX，发现禁止项即失败。分发前必须复核所有第三方依赖许可证及动态库替换条件；本地冒烟通过不等于授权发布。

## Windows（仅构建步骤，未构建）

须在 Windows 原生 Python 环境或单独授权的 Windows CI 上构建，不能用 Linux PyInstaller 直接生成 Windows 可执行文件。检出项目、安装 Node、执行 `npm ci --registry=https://registry.npmmirror.com` 与 `npm run build`，在 Python 3.11+ 虚拟环境执行 `pip install -e ".[dev,bundle,desktop]"` 和 `python packaging/build_desktop.py`。核查目录排除项与许可证后，在隔离 Windows 主机测试回环访问与界面。Windows 构建、远程 CI 推送和任何发布均需另行批准，本次均未进行。
