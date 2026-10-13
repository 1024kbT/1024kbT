"""使用杭州的实时天气和上海时区控制贡献小屋的天空。"""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request
from collections import Counter
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# 只查询本人所在地杭州，避免继续显示法国天气。
CITIES = {
    "Hangzhou": (30.2741, 120.1551),
}

PHASES = ("night", "dawn", "day", "dusk")
WEATHERS = ("clear", "cloudy", "fog", "rain", "snow", "storm")   # also the tie-break order (last wins)

LABELS = {
    "clear": ("clear sky", "晴", "☀️"), "cloudy": ("cloudy", "多云", "☁️"),
    "fog": ("fog", "雾", "🌫️"), "rain": ("rain", "雨", "🌧️"),
    "snow": ("snow", "雪", "🌨️"), "storm": ("thunderstorm", "雷雨", "⛈️"),
}
PHASE_LABELS = {"night": ("night", "夜晚", "🌙"), "dawn": ("dawn", "黎明", "🌅"),
                "day": ("day", "白天", "🏙️"), "dusk": ("dusk", "黄昏", "🌆")}


def weather_kind(code: int) -> str:
    if code in (0, 1):
        return "clear"
    if code in (2, 3):
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    return "cloudy"


def phase_at(now: dt.datetime, sunrise: dt.datetime, sunset: dt.datetime) -> str:
    margin = dt.timedelta(minutes=45)
    if sunrise - margin <= now <= sunrise + margin:
        return "dawn"
    if sunset - margin <= now <= sunset + margin:
        return "dusk"
    return "day" if sunrise < now < sunset else "night"


def fetch(now: dt.datetime) -> dict:
    lats = ",".join(str(c[0]) for c in CITIES.values())
    lons = ",".join(str(c[1]) for c in CITIES.values())
    qs = urllib.parse.urlencode({
        "latitude": lats, "longitude": lons, "timezone": "Asia/Shanghai", "forecast_days": 1,
        "current": "temperature_2m,weather_code,cloud_cover", "daily": "sunrise,sunset",
    })
    req = urllib.request.Request(f"https://api.open-meteo.com/v1/forecast?{qs}",
                                 headers={"User-Agent": "homelab-os-profile"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.load(resp)
    # 单城市响应为对象，多城市响应为数组，两种格式都可读取。
    rows = rows if isinstance(rows, list) else [rows]
    kinds = [weather_kind(r["current"]["weather_code"]) for r in rows]
    counts = Counter(kinds)
    kind = max(counts, key=lambda k: (counts[k], WEATHERS.index(k)))
    local = rows[0]["daily"]
    rise = dt.datetime.fromisoformat(local["sunrise"][0]).replace(tzinfo=LOCAL_TZ)
    sset = dt.datetime.fromisoformat(local["sunset"][0]).replace(tzinfo=LOCAL_TZ)
    return {
        "phase": phase_at(now, rise, sset),
        "weather": kind,
        "temp": sum(r["current"]["temperature_2m"] for r in rows) / len(rows),
        "cloud": sum(r["current"]["cloud_cover"] for r in rows) / len(rows),
        "cities": len(rows),
        "source": "Open-Meteo",
    }


def fallback(now: dt.datetime) -> dict:
    """No network: guess the phase from the clock, no weather effects."""
    rise = now.replace(hour=7, minute=30, second=0, microsecond=0)
    sset = now.replace(hour=19, minute=0, second=0, microsecond=0)
    return {"phase": phase_at(now, rise, sset), "weather": None, "temp": None, "cloud": 30,
            "cities": 0, "source": None}


def load(offline: bool, phase: str | None = None, weather: str | None = None) -> dict:
    now = dt.datetime.now(LOCAL_TZ)
    env = fallback(now)
    if not offline:
        try:
            env = fetch(now)
        except Exception as exc:  # 天气只是装饰，网络失败时保留基于时钟的昼夜效果。
            print(f"天气暂不可用（{exc}），使用时钟推算昼夜")
    if phase:
        env["phase"] = phase
    if weather:
        env["weather"] = weather
        env["cloud"] = {"clear": 5, "cloudy": 75, "fog": 90}.get(weather, 95)
        env.setdefault("temp", None)
        if env["temp"] is None:
            env["temp"] = {"snow": -1.0, "storm": 22.0}.get(weather, 12.0)
    return env


def describe(env: dict) -> tuple[str, str]:
    """返回英文、中文两种天空说明。"""
    p_en, p_fr, p_icon = PHASE_LABELS[env["phase"]]
    if not env["weather"]:
        return f"{p_icon} {p_en}", f"{p_icon} {p_fr}"
    w_en, w_fr, w_icon = LABELS[env["weather"]]
    if env["weather"] == "clear" and env["phase"] != "day":
        w_icon = "🌙"
    t = f"{env['temp']:.0f}°C"
    return f"{w_icon} Hangzhou {t} · {w_en} · {p_en}", f"{w_icon} 杭州 {t} · {w_fr} · {p_fr}"
