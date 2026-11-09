# 四城市 TMYx 来源及校验

检索国内镜像时未找到能核验版本和哈希的可靠镜像，故从 Climate.OneBuilding 官方站使用 TLS 下载；TMYx 为 NOAA ISD 逐时资料经 TMY 方法处理，本站 2026 年发布的数据说明另包含 ERA5 辐射。每个文件选取 2007–2021 时段，典型年由不同时段月份拼接，并不代表某个实际自然年。运行环境中 ZIP 与 EPW 仅放被 Git 忽略的 `build/weather/`，不入库。

| 城市与测站 | 官方下载地址 | 本次 ZIP SHA256 |
|---|---|---|
| 哈尔滨太平机场 541611 | https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/HL_Heilongjiang/CHN_HL_Harbin-Taiping.AP.541611_TMYx.2007-2021.zip | `e1ec1363b302f1146a68c05efea4546f04078ad341cc4ce70ab1899453a60474` |
| 北京首都机场 545110 | https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/BJ_Beijing/CHN_BJ_Beijing-Capital.Intl.AP.545110_TMYx.2007-2021.zip | `fa8f7607821fe267de1459c28fd6b52d830e032b9ef4ee603d4d64008600178b` |
| 上海虹桥机场 583670 | https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SH_Shanghai/CHN_SH_Shanghai-Hongqiao.Intl.AP.583670_TMYx.2007-2021.zip | `5e0f03947ac8cec96b94ba49841c61d6a46da61aab3f048dbf1fde0b63bdb028` |
| 广州 592870 | https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/GD_Guangdong/CHN_GD_Guangzhou.592870_TMYx.2007-2021.zip | `a9d5fd42e53087f50049eff6a481e8b5706573ca8e9513d41e88a4bfbb4a2ccf` |

这些 SHA256 在本次官方 TLS 下载后计算，并固定于 `tools/fetch_tmyx.py`；不是官方已签名的预发布哈希。ZIP 内容额外做 CRC 检查，解压 EPW 的 SHA256 及原始文件名写在构建目录 `manifest.json`；各算例 JSON 的 `provenance.data_sha256` 记录实际使用的 EPW 散列。若上游同名文件更新而散列不符，脚本拒绝覆盖并要求人工核查，不能绕过 TLS 或完整性检查。

**许可说明：**站点提供免费下载及引用建议（Lawrie, Linda K. and Drury B. Crawley, Climate.OneBuilding.org）；站点页声明版权，现未核实可再分发授权或独立许可证，不能仅凭免费获得认定可再分发。NOAA ISD 和 ERA5 各自还须遵守来源条件。本项目因此不随软件分发气象文件，仅提供用户自行获取方式；发布前应由复核人员复核再分发权限。这比开发方案中的“可再分发”假定更保守，不改变书稿。

下载任务记录：`journalctl --user -u orv-energy-study-weather`。未配置 `ORV_WEATHER_DIR` 的自动测试仅跳过真实气象读取，仍执行合成 EPW 和能量基准。
