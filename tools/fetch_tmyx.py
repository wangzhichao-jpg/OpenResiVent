"""从 Climate.OneBuilding 获取四城市 TMYx；文件只写被忽略的 build/。"""

import hashlib
import json
import ssl
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/weather"
BASE = "https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/"
SOURCES = {
    "harbin": "HL_Heilongjiang/CHN_HL_Harbin-Taiping.AP.541611_TMYx.2007-2021.zip",
    "beijing": "BJ_Beijing/CHN_BJ_Beijing-Capital.Intl.AP.545110_TMYx.2007-2021.zip",
    "shanghai": "SH_Shanghai/CHN_SH_Shanghai-Hongqiao.Intl.AP.583670_TMYx.2007-2021.zip",
    "guangzhou": "GD_Guangdong/CHN_GD_Guangzhou.592870_TMYx.2007-2021.zip",
}
# 首次从官方 TLS 来源获取后记录的 ZIP SHA256，重跑须一致。
SHA256 = {
    "harbin": "e1ec1363b302f1146a68c05efea4546f04078ad341cc4ce70ab1899453a60474",
    "beijing": "fa8f7607821fe267de1459c28fd6b52d830e032b9ef4ee603d4d64008600178b",
    "shanghai": "5e0f03947ac8cec96b94ba49841c61d6a46da61aab3f048dbf1fde0b63bdb028",
    "guangzhou": "a9d5fd42e53087f50049eff6a481e8b5706573ca8e9513d41e88a4bfbb4a2ccf",
}


def main():
    """获取原 ZIP、校验散列与 ZIP CRC，解压单个 EPW，写本地清单。"""
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    for city, relative in SOURCES.items():
        url = BASE + relative
        with urllib.request.urlopen(
            url, timeout=60, context=ssl.create_default_context()
        ) as response:
            payload = response.read()
        digest = hashlib.sha256(payload).hexdigest()
        if city in SHA256 and digest != SHA256[city]:
            raise ValueError(f"{city} 官方 ZIP 哈希变化，拒绝覆盖；须复核来源和版本")
        archive = OUT / (city + ".zip")
        archive.write_bytes(payload)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise ValueError(f"{city} ZIP CRC 校验失败")
            entries = [item for item in z.infolist() if item.filename.lower().endswith(".epw")]
            if len(entries) != 1:
                raise ValueError(f"{city} EPW 文件数非 1")
            epw = z.read(entries[0])
        (OUT / (city + ".epw")).write_bytes(epw)
        records[city] = {
            "url": url,
            "zip_sha256": digest,
            "epw_sha256": hashlib.sha256(epw).hexdigest(),
            "epw_name": entries[0].filename,
        }
        print(city, digest, flush=True)
    (OUT / "manifest.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )


if __name__ == "__main__":
    main()
