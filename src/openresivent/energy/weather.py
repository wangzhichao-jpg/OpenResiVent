"""EPW 标准逐时气象解析；外部文件仅通过明确路径读取。"""

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from openresivent.core.psychrometrics import humidity_ratio


@dataclass(frozen=True)
class WeatherHour:
    """月份、日期、时刻（EPW 1–24）、温度 K、含湿量 kg/kg 干空气、气压 Pa。"""

    month: int
    day: int
    hour: int
    temperature: float
    humidity_ratio: float
    pressure: float = 101325


def read_epw(path: Path, *, require_year: bool = True) -> list[WeatherHour]:
    """读取 EPW 的逐时干球、相对湿度和气压；缺测及错误明确拒绝。"""
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        for _ in range(8):
            if next(reader, None) is None:
                raise ValueError("EPW 头部不足 8 行")
        for lineno, row in enumerate(reader, 9):
            if not row:
                continue
            try:
                m, d, h = int(row[1]), int(row[2]), int(row[3])
                t = float(row[6])
                rh = float(row[8])
                p = float(row[9])
                if not (
                    1 <= m <= 12
                    and 1 <= d <= 31
                    and 1 <= h <= 24
                    and -70 < t < 70
                    and 0 <= rh <= 100
                    and 30000 < p < 120000
                ):
                    raise ValueError("气象数据无效或缺测")
                w = humidity_ratio(t + 273.15, rh / 100, p)
                rows.append(WeatherHour(m, d, h, t + 273.15, w, p))
            except (IndexError, ValueError) as exc:
                raise ValueError(f"EPW 第 {lineno} 行无效：{exc}") from exc
    if require_year and len(rows) != 8760:
        raise ValueError(f"EPW 需为 8760 个逐时值，实际 {len(rows)}")
    if require_year:
        for i, row in enumerate(rows):
            expected = datetime(2001, 1, 1) + timedelta(hours=i)
            if (row.month, row.day, row.hour) != (expected.month, expected.day, expected.hour + 1):
                raise ValueError(f"EPW 逐时序列在第 {i + 1} 条存在缺失、重复或乱序")
    return rows
