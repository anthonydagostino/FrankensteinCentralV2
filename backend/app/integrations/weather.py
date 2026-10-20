"""Weather: Open-Meteo forecast plus National Weather Service alerts."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from ..config_loader import Location
from ..util import iso, local_tz, utcnow
from .base import BaseIntegration, Degraded, describe_error, load_fixture, make_client, request
from .wmo import describe

log = logging.getLogger("frankenstein.weather")

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY = "https://air-quality-api.open-meteo.com/v1/air-quality"
NWS_ALERTS = "https://api.weather.gov/alerts/active"

FORECAST_TTL = 15 * 60

FIXTURE_ANCHOR = "2026-10-20"


def _units_params(units: str) -> dict[str, str]:
    if units == "metric":
        return {"temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm"}
    return {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"}


def _r(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def parse_forecast(raw: dict, now: datetime, units: str = "imperial") -> dict:
    """Turn an Open-Meteo response into the dashboard shape (without alerts)."""
    tz = local_tz()
    cur = raw.get("current", {}) or {}
    is_day = bool(cur.get("is_day", 1))
    label, icon = describe(cur.get("weather_code"), is_day)
    current = {
        "temp": _r(cur.get("temperature_2m")),
        "feels_like": _r(cur.get("apparent_temperature")),
        "humidity": _r(cur.get("relative_humidity_2m")),
        "code": cur.get("weather_code"),
        "label": label,
        "icon": icon,
        "is_day": is_day,
        "wind_mph": _r(cur.get("wind_speed_10m")),
        "gust_mph": _r(cur.get("wind_gusts_10m")),
        "precip_in": float(cur.get("precipitation") or 0),
    }

    hourly = raw.get("hourly", {}) or {}
    times = hourly.get("time", []) or []
    local_now = now.astimezone(tz)
    start_hour = local_now.replace(minute=0, second=0, microsecond=0)
    next_12h: list[dict] = []
    for idx, t in enumerate(times):
        try:
            ht = datetime.fromisoformat(t)
        except ValueError:
            continue
        if ht.tzinfo is None:
            ht = ht.replace(tzinfo=tz)
        if ht < start_hour:
            continue
        hcode = (hourly.get("weather_code") or [None] * len(times))[idx]
        # hourly is_day is not requested; approximate with sunrise/sunset of the day
        h_is_day = True
        daily_raw = raw.get("daily", {}) or {}
        for d_idx, d in enumerate(daily_raw.get("time", []) or []):
            if d == ht.date().isoformat():
                try:
                    sr = datetime.fromisoformat(daily_raw["sunrise"][d_idx]).replace(tzinfo=tz)
                    ss = datetime.fromisoformat(daily_raw["sunset"][d_idx]).replace(tzinfo=tz)
                    h_is_day = sr <= ht <= ss
                except (KeyError, ValueError, IndexError, TypeError):
                    pass
                break
        hl, hi = describe(hcode, h_is_day)
        next_12h.append(
            {
                "time": iso(ht),
                "temp": _r((hourly.get("temperature_2m") or [None] * len(times))[idx]),
                "pop": _r((hourly.get("precipitation_probability") or [0] * len(times))[idx]) or 0,
                "code": hcode,
                "icon": hi,
                "wind_mph": _r((hourly.get("wind_speed_10m") or [None] * len(times))[idx]),
            }
        )
        if len(next_12h) >= 12:
            break

    daily_raw = raw.get("daily", {}) or {}
    daily: list[dict] = []
    for idx, d in enumerate(daily_raw.get("time", []) or []):
        dl, di = describe((daily_raw.get("weather_code") or [None])[idx], True)
        daily.append(
            {
                "date": d,
                "hi": _r((daily_raw.get("temperature_2m_max") or [None])[idx]),
                "lo": _r((daily_raw.get("temperature_2m_min") or [None])[idx]),
                "pop": _r((daily_raw.get("precipitation_probability_max") or [0])[idx]) or 0,
                "precip": float((daily_raw.get("precipitation_sum") or [0])[idx] or 0),
                "code": (daily_raw.get("weather_code") or [None])[idx],
                "label": dl,
                "icon": di,
                "sunrise": (daily_raw.get("sunrise") or [None])[idx],
                "sunset": (daily_raw.get("sunset") or [None])[idx],
                "uv": (daily_raw.get("uv_index_max") or [None])[idx],
                "wind_max": _r((daily_raw.get("wind_speed_10m_max") or [None])[idx]),
            }
        )

    badges: list[str] = []
    if any((h.get("pop") or 0) >= 50 for h in next_12h):
        badges.append("umbrella")
    gust = current.get("gust_mph") or 0
    gust_threshold = 56 if units == "metric" else 35
    if gust >= gust_threshold:
        badges.append("wind")
    freeze_point = 0 if units == "metric" else 32
    if daily and daily[0].get("lo") is not None and daily[0]["lo"] <= freeze_point:
        badges.append("freeze")
    if daily and daily[0].get("uv") is not None and float(daily[0]["uv"]) >= 7:
        badges.append("uv")

    return {"current": current, "next_12h": next_12h, "daily": daily, "badges": badges, "units": units}


SEVERITY_ORDER = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}


def parse_alerts(raw: dict) -> list[dict]:
    alerts = []
    for feature in raw.get("features", []) or []:
        p = feature.get("properties", {}) or {}
        alerts.append(
            {
                "id": feature.get("id") or p.get("id"),
                "event": p.get("event"),
                "severity": p.get("severity") or "Unknown",
                "urgency": p.get("urgency"),
                "headline": p.get("headline"),
                "description": p.get("description"),
                "instruction": p.get("instruction"),
                "effective": p.get("effective"),
                "expires": p.get("expires"),
                "area": p.get("areaDesc"),
            }
        )
    alerts.sort(key=lambda a: SEVERITY_ORDER.get(a["severity"], 4))
    return alerts


class WeatherIntegration(BaseIntegration):
    name = "weather"
    interval_seconds = 5 * 60  # NWS cadence; forecast is re-fetched every 15 minutes
    required_env: list[str] = []  # no credentials needed

    def __init__(self, settings, config):
        super().__init__(settings, config)
        self._forecast_cache: dict[str, tuple[datetime, dict]] = {}
        self._aqi_cache: dict[str, tuple[datetime, int | None]] = {}

    def is_configured(self) -> bool:
        return bool(self.config.weather.locations)

    def setup_hint(self) -> list[str]:
        return ["NWS_USER_AGENT"]

    async def _forecast(self, client, loc: Location, now: datetime) -> dict:
        cached = self._forecast_cache.get(loc.name)
        if cached and (now - cached[0]).total_seconds() < FORECAST_TTL:
            return cached[1]
        params = {
            "latitude": loc.lat,
            "longitude": loc.lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day,precipitation,wind_speed_10m,wind_gusts_10m",
            "hourly": "temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,sunrise,sunset,uv_index_max,wind_speed_10m_max",
            "timezone": self.config.timezone,
            "forecast_days": 7,
            **_units_params(self.config.weather.units),
        }
        resp = await request(client, "GET", OPEN_METEO, params=params, service="Open-Meteo")
        resp.raise_for_status()
        raw = resp.json()
        self._forecast_cache[loc.name] = (now, raw)
        return raw

    async def _aqi(self, client, loc: Location, now: datetime) -> int | None:
        cached = self._aqi_cache.get(loc.name)
        if cached and (now - cached[0]).total_seconds() < FORECAST_TTL * 4:
            return cached[1]
        try:
            resp = await request(client, "GET", AIR_QUALITY, params={"latitude": loc.lat, "longitude": loc.lon, "current": "us_aqi"}, retries=0, service="Open-Meteo air quality")
            resp.raise_for_status()
            value = resp.json().get("current", {}).get("us_aqi")
            aqi = int(value) if value is not None else None
        except Exception:
            aqi = None
        self._aqi_cache[loc.name] = (now, aqi)
        return aqi

    async def _alerts(self, client, loc: Location) -> list[dict]:
        headers = {"User-Agent": self.settings.nws_user_agent, "Accept": "application/geo+json"}
        resp = await request(client, "GET", NWS_ALERTS, params={"point": f"{loc.lat},{loc.lon}"}, headers=headers, service="NWS")
        resp.raise_for_status()
        return parse_alerts(resp.json())

    async def fetch(self) -> dict:
        now = utcnow()
        units = self.config.weather.units
        out: dict[str, dict] = {}
        errors: list[str] = []
        async with make_client() as client:
            for loc in self.config.weather.locations:
                entry: dict = {"location": loc.name, "lat": loc.lat, "lon": loc.lon}
                try:
                    raw = await self._forecast(client, loc, now)
                    entry.update(parse_forecast(raw, now, units))
                except Exception as exc:
                    errors.append(f"{loc.name}: {describe_error(exc, 'Open-Meteo')}")
                    continue
                try:
                    entry["alerts"] = await self._alerts(client, loc)
                except Exception as exc:
                    entry["alerts"] = []
                    entry["alerts_error"] = describe_error(exc, "NWS")
                    errors.append(f"{loc.name} alerts: {entry['alerts_error']}")
                entry["aqi"] = await self._aqi(client, loc, now)
                out[loc.name] = entry
        data = {"locations": out, "default": self.config.weather.default_location.name, "units": units}
        if not out:
            raise RuntimeError("; ".join(errors) or "no forecast")
        if errors:
            raise Degraded(data, "; ".join(errors))
        return data

    def mock(self) -> dict:
        now = utcnow()
        units = self.config.weather.units
        raw = load_fixture("weather/open_meteo.json")
        raw = _shift_forecast_dates(raw, now)
        nws = load_fixture("weather/nws_alerts.json")
        alerts = parse_alerts(nws)
        for a in alerts:
            a["expires"] = iso(now + timedelta(hours=9))
            a["effective"] = iso(now - timedelta(hours=1))
        out = {}
        for idx, loc in enumerate(self.config.weather.locations):
            entry = {"location": loc.name, "lat": loc.lat, "lon": loc.lon}
            entry.update(parse_forecast(raw, now, units))
            entry["alerts"] = alerts if idx == 0 else []
            entry["aqi"] = 42
            out[loc.name] = entry
        return {"locations": out, "default": self.config.weather.default_location.name, "units": units}


def _shift_forecast_dates(raw: dict, now: datetime) -> dict:
    """Re-base a fixture anchored on FIXTURE_ANCHOR so hourly/daily arrays cover today."""
    from datetime import date

    tz = local_tz()
    anchor = date.fromisoformat(raw.get("_anchor", FIXTURE_ANCHOR))
    today = now.astimezone(tz).date()
    delta = today - anchor

    def shift(value: str) -> str:
        if not value:
            return value
        if len(value) == 10:
            return (date.fromisoformat(value) + delta).isoformat()
        dt = datetime.fromisoformat(value)
        return (dt + delta).isoformat(timespec="minutes")

    out = {k: v for k, v in raw.items() if not k.startswith("_")}
    hourly = dict(out.get("hourly", {}))
    hourly["time"] = [shift(t) for t in hourly.get("time", [])]
    out["hourly"] = hourly
    daily = dict(out.get("daily", {}))
    daily["time"] = [shift(t) for t in daily.get("time", [])]
    for key in ("sunrise", "sunset"):
        if key in daily:
            daily[key] = [shift(t) for t in daily[key]]
    out["daily"] = daily
    cur = dict(out.get("current", {}))
    local_now = now.astimezone(tz)
    cur["time"] = local_now.strftime("%Y-%m-%dT%H:%M")
    cur["is_day"] = 1 if 7 <= local_now.hour < 18 else 0
    out["current"] = cur
    return out
