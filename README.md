# OpenResiVent 住宅通风计算软件

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
