"""Hourly forecast at the start of the trip: temperature, rain chance, air quality, daylight (Open-Meteo, no key)."""
from .core import cached_get


def conditions(lat, lng, when):
    day = when.strftime("%Y-%m-%d")
    hour = when.strftime("%Y-%m-%dT%H:00")
    out = {"source": "Open-Meteo forecast", "hour": when.strftime("%-I %p")}
    try:
        w = cached_get("meteo", f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}"
                       f"&hourly=temperature_2m,precipitation_probability,is_day&timezone=America/Los_Angeles"
                       f"&start_date={day}&end_date={day}")["hourly"]
        i = w["time"].index(hour)
        out.update(temp_c=w["temperature_2m"][i], rain_pct=w["precipitation_probability"][i], daylight=bool(w["is_day"][i]))
    except Exception:
        out["weather"] = "no information"
    try:
        a = cached_get("meteo-aq", f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lng}"
                       f"&hourly=us_aqi&timezone=America/Los_Angeles&start_date={day}&end_date={day}")["hourly"]
        out["aqi"] = a["us_aqi"][a["time"].index(hour)]
    except Exception:
        out["aqi"] = None
    return out
