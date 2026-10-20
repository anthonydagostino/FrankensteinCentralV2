"""WMO weather code map (Open-Meteo weather_code) to label and lucide icon."""

from __future__ import annotations

_MAP: dict[int, tuple[str, str, str]] = {
    0: ("Clear", "sun", "moon"),
    1: ("Mostly clear", "sun", "moon"),
    2: ("Partly cloudy", "cloud-sun", "cloud-moon"),
    3: ("Overcast", "cloud", "cloud"),
    45: ("Fog", "cloud-fog", "cloud-fog"),
    48: ("Fog", "cloud-fog", "cloud-fog"),
    51: ("Drizzle", "cloud-drizzle", "cloud-drizzle"),
    53: ("Drizzle", "cloud-drizzle", "cloud-drizzle"),
    55: ("Drizzle", "cloud-drizzle", "cloud-drizzle"),
    56: ("Freezing drizzle", "cloud-drizzle", "cloud-drizzle"),
    57: ("Freezing drizzle", "cloud-drizzle", "cloud-drizzle"),
    61: ("Light rain", "cloud-rain", "cloud-rain"),
    63: ("Rain", "cloud-rain", "cloud-rain"),
    65: ("Heavy rain", "cloud-rain", "cloud-rain"),
    66: ("Freezing rain", "cloud-hail", "cloud-hail"),
    67: ("Freezing rain", "cloud-hail", "cloud-hail"),
    71: ("Light snow", "cloud-snow", "cloud-snow"),
    73: ("Snow", "cloud-snow", "cloud-snow"),
    75: ("Heavy snow", "cloud-snow", "cloud-snow"),
    77: ("Snow grains", "cloud-snow", "cloud-snow"),
    80: ("Rain showers", "cloud-rain-wind", "cloud-rain-wind"),
    81: ("Rain showers", "cloud-rain-wind", "cloud-rain-wind"),
    82: ("Heavy rain showers", "cloud-rain-wind", "cloud-rain-wind"),
    85: ("Snow showers", "cloud-snow", "cloud-snow"),
    86: ("Snow showers", "cloud-snow", "cloud-snow"),
    95: ("Thunderstorm", "cloud-lightning", "cloud-lightning"),
    96: ("Thunderstorm with hail", "cloud-lightning", "cloud-lightning"),
    99: ("Thunderstorm with hail", "cloud-lightning", "cloud-lightning"),
}


def describe(code: int | None, is_day: bool = True) -> tuple[str, str]:
    """Return (label, icon) for a WMO code."""
    if code is None:
        return ("Unknown", "cloud")
    entry = _MAP.get(int(code))
    if entry is None:
        return ("Unknown", "cloud")
    label, day_icon, night_icon = entry
    return (label, day_icon if is_day else night_icon)
