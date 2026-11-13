# OpenResiVent: 住宅通风计算与校核工具

用于住宅新风量核算、户内压差分析、排风补风校核与风管声学校核的开源工程计算工具。

[English](README.md) | 简体中文

[![Release](https://img.shields.io/github/v/release/wangzhichao-jpg/OpenResiVent?include_prereleases&label=Release)](https://github.com/wangzhichao-jpg/OpenResiVent/releases)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](pyproject.toml)

[GitHub 仓库](https://github.com/wangzhichao-jpg/OpenResiVent) · [Gitee 仓库](https://gitee.com/bigtaurus/OpenResiVent)

![OpenResiVent 住宅通风一户完整校核向导与计算结果](docs/images/household_check.png)

## 适用人群与用途

- **住宅通风与建筑暖通设计人员**：用于全户新风量核算、多居室风量分配、厨房与卫生间排风补风方案校核及风管水力阻力计算。
- **住宅通风与室内空气品质（IAQ）研究人员**：用于多区域管网稳态流动求解、门窗缝隙与开口等效面积计算、油烟机大排风下的户内门窗压差预测及滤网积尘阻力衰减分析。
- **新风设备研发与技术支持人员**：用于产品检测数据处理（风机定律与效率折算）及参数扫描敏感性分析。
- **标准编制、专著与教学算例复核人员**：提供完整的一户校核向导、规范条文对照及合并报告生成（DOCX、JSON、CSV）。

## 主要功能

- **一户完整校核向导（`resivent check`）**：支持全屋新风量设计校核、户内压差与排风补风校核、卧室噪声初算、条文汇总与工程报告生成（DOCX 与 JSON 格式）。
- **新风量与多区网络流动**：支持换气次数法与人均风量法核算需求风量；求解稳态充分混合多区压力与路径流量，结合门窗缝隙与开口等效面积进行计算。
- **户内压差与排风补风**：油烟机/排风扇开启时门窗压差预测与机械/自然补风量反算校核。
- **风管水力阻力与滤网衰减**：直管阻力与局部阻力计算，支持基于滤网积尘质量守恒周期模型估算阻力衰减。
- **卧室噪声初筛估算**：包含 63 Hz 至 8 kHz 八频带风机声功率级、直管与弯头衰减及室内 A 声级预测。
- **多工况参数扫描（`resivent sweep`）**：全因子或拉丁超立方抽样，计算分组达标率与敏感性排序，结果存入 SQLite 并导出 CSV/XLSX/DOCX。
- **产品检测数据处理**：风机转速换算与非等风量效率折算。
- **本地 Web 界面与服务**：内置本地 Web 交互界面（`resivent serve`，默认仅监听 127.0.0.1）。

## 快速开始

### 1. 从 Release 下载并安装

需要 Python 3.11 及以上版本。从官方发行版页面（[GitHub Releases](https://github.com/wangzhichao-jpg/OpenResiVent/releases) 或 [Gitee 发行版](https://gitee.com/bigtaurus/OpenResiVent/releases)）下载预编译 wheel：

- 附件文件名：`openresivent-0.5.0rc2-py3-none-any.whl`
- SHA256 校验码：`ea9df32cd161cddfa7df30f27710cae9b1ce68741946bd2dfa4a5a7c3d046b87`

在虚拟环境中进行校验与安装：

```bash
# 1. 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Windows 用户使用: .venv\Scripts\activate

# 2. 校验文件完整性 (Linux/macOS)
echo "ea9df32cd161cddfa7df30f27710cae9b1ce68741946bd2dfa4a5a7c3d046b87  openresivent-0.5.0rc2-py3-none-any.whl" | sha256sum -c

# 3. 安装 wheel 包
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple ./openresivent-0.5.0rc2-py3-none-any.whl

# 4. 检查安装版本
resivent --version
```

### 2. 运行示例与启动本地服务

```bash
# 运行一户通风校核示例并生成结果
resivent run cases/book/ch02/ex2-01.yaml --out results

# 启动本地 Web 交互界面（默认仅监听 127.0.0.1 且无认证，请勿直接暴露公网）
resivent serve

# 执行多工况参数扫描计算
resivent sweep cases/studies/makeup_sweep.yaml --out results/sweep
```

## 验证与当前状态

### 算法验证与测试

基础物性、解析解及公开文献典型工况已建立自动化测试回归；二阶有界离散格式空气龄示例通过网格敏感性校验；相关测试与验证记录详见 [docs/site/validation.md](docs/site/validation.md)。

### 定性说明与结果边界

本版为公开测评候选版，不是经认证的设计软件；请先核对公式、单位、参数和适用范围。

示例风机、户型气密性、声源、风管衰减和部分环境参数是示例或假设；扫描的等权组合比例不是群体概率。气象文件及外部求解程序不随软件提供。风管声学完整路径尚无完全等价的公开例题对照；所有输出不能替代现场检测、安全评估或设计审查。

## 文档、引用与许可

- **使用文档**：详见 [使用说明](docs/site/user.md) 与 [下载与安装说明](docs/site/下载与安装.md)。
- **引用信息**：如在学术研究或著作中引用，请参考 `CITATION.cff`（引用信息草稿，正式发布前核对）。
- **开源许可证**：核心代码按 Apache-2.0 许可；数据、文档及算例按 CC BY 4.0 许可，详见 LICENSE、NOTICE 和 THIRD_PARTY_NOTICES。
- **联系与反馈**：欢迎通过 [GitHub Issues](https://github.com/wangzhichao-jpg/OpenResiVent/issues) 或 [Gitee Issues](https://gitee.com/bigtaurus/OpenResiVent/issues) 提交可复现的问题、输入和输出；请勿上传个人隐私或未获授权的数据。
