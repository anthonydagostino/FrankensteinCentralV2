"""Generate the Open-Meteo and NWS fixtures (anchored on 2026-10-20). Run: python -m app.fixtures.generate_weather"""

import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANCHOR = date(2026, 10, 20)


def build_open_meteo() -> dict:
    rnd = random.Random(42)
    hourly_time, temps, pops, codes, winds = [], [], [], [], []
    daily = {"time": [], "weather_code": [], "temperature_2m_max": [], "temperature_2m_min": [], "precipitation_probability_max": [], "precipitation_sum": [], "sunrise": [], "sunset": [], "uv_index_max": [], "wind_speed_10m_max": []}
    day_codes = [3, 61, 2, 0, 1, 80, 2]
    for d in range(7):
        day = ANCHOR + timedelta(days=d)
        base_hi = 63 - d * 1.5 + rnd.uniform(-3, 3)
        base_lo = base_hi - 15
        day_pop = [10, 70, 20, 0, 5, 60, 15][d]
        daily["time"].append(day.isoformat())
        daily["weather_code"].append(day_codes[d])
        daily["temperature_2m_max"].append(round(base_hi, 1))
        daily["temperature_2m_min"].append(round(base_lo, 1))
        daily["precipitation_probability_max"].append(day_pop)
        daily["precipitation_sum"].append(round(0.45 if day_pop >= 60 else 0.0, 2))
        daily["sunrise"].append(f"{day.isoformat()}T07:{12 + d:02d}")
        daily["sunset"].append(f"{day.isoformat()}T18:{10 - d:02d}")
        daily["uv_index_max"].append([3.2, 1.5, 4.0, 4.5, 4.1, 2.0, 3.8][d])
        daily["wind_speed_10m_max"].append([18, 24, 12, 9, 11, 21, 14][d])
        for h in range(24):
            t = datetime(day.year, day.month, day.day, h)
            hourly_time.append(t.strftime("%Y-%m-%dT%H:%M"))
            temp = base_lo + (base_hi - base_lo) * (0.5 - 0.5 * math.cos((h - 5) / 24 * 2 * math.pi))
            temps.append(round(temp + rnd.uniform(-1, 1), 1))
            if day_pop >= 60:
                pop = int(max(0, min(100, day_pop + 25 * math.sin((h - 8) / 10 * math.pi))))
            else:
                pop = int(max(0, day_pop + rnd.uniform(-5, 10)))
            pops.append(pop)
            codes.append(61 if pop >= 55 else (3 if pop >= 30 else day_codes[d]))
            winds.append(round(6 + 8 * rnd.random(), 1))
    return {
        "_anchor": ANCHOR.isoformat(),
        "latitude": 39.95,
        "longitude": -74.2,
        "timezone": "America/New_York",
        "current_units": {"temperature_2m": "°F", "wind_speed_10m": "mp/h", "precipitation": "inch"},
        "current": {"time": f"{ANCHOR.isoformat()}T16:45", "interval": 900, "temperature_2m": 58.3, "apparent_temperature": 55.1, "relative_humidity_2m": 71, "weather_code": 3, "is_day": 1, "precipitation": 0.0, "wind_speed_10m": 9.4, "wind_gusts_10m": 18.2},
        "hourly_units": {"temperature_2m": "°F", "precipitation_probability": "%"},
        "hourly": {"time": hourly_time, "temperature_2m": temps, "precipitation_probability": pops, "weather_code": codes, "wind_speed_10m": winds},
        "daily_units": {"temperature_2m_max": "°F"},
        "daily": daily,
    }


def build_nws() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "https://api.weather.gov/alerts/urn:oid:2.49.0.1.840.0.mock.001",
                "type": "Feature",
                "properties": {
                    "id": "urn:oid:2.49.0.1.840.0.mock.001",
                    "areaDesc": "Ocean; Eastern Monmouth",
                    "event": "Wind Advisory",
                    "severity": "Moderate",
                    "certainty": "Likely",
                    "urgency": "Expected",
                    "headline": "Wind Advisory issued October 20 at 3:12PM EDT until October 21 at 2:00AM EDT by NWS Mount Holly NJ",
                    "description": "* WHAT...Northwest winds 20 to 30 mph with gusts up to 45 mph expected.\n\n* WHERE...Ocean and Eastern Monmouth counties.\n\n* WHEN...Until 2 AM EDT Tuesday.\n\n* IMPACTS...Gusty winds could blow around unsecured objects. Tree limbs could be blown down and a few power outages may result.",
                    "instruction": "Use extra caution when driving, especially if operating a high profile vehicle. Secure outdoor objects.",
                    "effective": "2026-10-20T15:12:00-04:00",
                    "expires": "2026-10-21T02:00:00-04:00",
                    "senderName": "NWS Mount Holly NJ",
                },
            }
        ],
        "title": "Current watches, warnings, and advisories for 39.9537 N, 74.1979 W",
    }


if __name__ == "__main__":
    (HERE / "weather").mkdir(exist_ok=True)
    (HERE / "weather" / "open_meteo.json").write_text(json.dumps(build_open_meteo(), indent=1))
    (HERE / "weather" / "nws_alerts.json").write_text(json.dumps(build_nws(), indent=1))
    print("weather fixtures written")
