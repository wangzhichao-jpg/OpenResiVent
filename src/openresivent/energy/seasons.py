"""吕伟华等 2023 第 13 页表 2 的四城市采暖/制冷季。"""

from openresivent.energy.weather import WeatherHour


def city_season(city: str, weather: WeatherHour) -> str:
    """城市及月日 → heating、cooling、off；端点按日期含首尾。"""
    md = (weather.month, weather.day)
    if city == "harbin":
        return "heating" if md >= (10, 15) or md <= (4, 15) else "off"
    if city == "beijing":
        return (
            "heating"
            if md >= (11, 15) or md <= (3, 15)
            else "cooling"
            if (6, 1) <= md <= (8, 31)
            else "off"
        )
    if city == "shanghai":
        return (
            "heating"
            if md >= (12, 1) or md <= (2, 28)
            else "cooling"
            if (6, 1) <= md <= (9, 30)
            else "off"
        )
    if city == "guangzhou":
        return "cooling" if (5, 1) <= md <= (10, 31) else "off"
    raise ValueError("未知城市")
