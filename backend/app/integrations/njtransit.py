"""NJ Transit rail departures between two stations, both directions, from the RailData API.

Read only. The API (https://raildata.njtransit.com/api/TrainData) is form-POST based: getToken turns the
developer username and password into a token (NJ Transit allows five new tokens per day, so the token is
kept on disk and only replaced when the API says it is invalid), getStationList maps station names to
their two letter codes, and getTrainSchedule lists the next trains leaving a station with their stops.

A train "goes" from A to B when B is among its remaining stops (direct). When it does not, but the
transfer station is, it is shown as "via <transfer>" (the Raritan Valley Line mostly ends at Newark
Penn, where NEC and NJCL trains continue to New York). Everything else leaving A is dropped.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..config_loader import DashboardConfig
from ..settings import Settings
from ..util import iso, local_tz, utcnow
from .base import BaseIntegration, load_fixture, make_client, request

log = logging.getLogger("frankenstein.transit")

BASE_URL = "https://raildata.njtransit.com/api/TrainData"
TOKENS_PER_DAY = 5
MAX_DEPARTURES = 6
TIME_FORMATS = ("%d-%b-%Y %I:%M:%S %p", "%m/%d/%Y %I:%M:%S %p", "%Y-%m-%dT%H:%M:%S")


class InvalidToken(Exception):
    """The API rejected the saved token."""


class TokenLimit(Exception):
    """Five tokens were already created today; the next refresh must wait for tomorrow."""


def parse_njt_time(value: str | None, tz: Any) -> datetime | None:
    """Aware datetime from the API's local time strings ("25-Nov-2026 07:12:00 AM"); None when unparsable."""
    if not value:
        return None
    text = value.strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)


def classify_status(status: str | None, delay_min: int) -> str:
    """One of cancelled, departed, boarding, delayed, on_time from the API's free text STATUS plus SEC_LATE."""
    text = (status or "").strip().lower()
    if "cancel" in text:
        return "cancelled"
    if "departed" in text:
        return "departed"
    if "boarding" in text or "all aboard" in text:
        return "boarding"
    if delay_min >= 3 or "late" in text or "delay" in text:
        return "delayed"
    return "on_time"


def _stop_matches(stop: dict[str, Any], station: dict[str, str]) -> bool:
    code = (stop.get("STATION_2CHAR") or "").strip().upper()
    if station["code"] and code:
        return code == station["code"]
    return (stop.get("STATIONNAME") or "").strip().lower() == station["name"].lower()


def direction_rows(
    items: list[dict[str, Any]], origin: dict[str, str], destination: dict[str, str], via: dict[str, str] | None, now: datetime, tz: Any
) -> list[dict[str, Any]]:
    """Departures from `origin` that reach `destination` directly or through `via`, soonest first."""
    rows: list[dict[str, Any]] = []
    for item in items:
        departs = parse_njt_time(item.get("SCHED_DEP_DATE"), tz)
        if departs is None:
            continue
        stops = item.get("STOPS") or []
        # only stops after the origin count: a train that already passed the destination is going the other way
        remaining: list[dict[str, Any]] = []
        seen_origin = False
        for stop in stops:
            if seen_origin:
                remaining.append(stop)
            elif _stop_matches(stop, origin):
                seen_origin = True
        if not seen_origin:
            remaining = stops
        direct = any(_stop_matches(s, destination) for s in remaining)
        transfer = bool(via) and not direct and any(_stop_matches(s, via) for s in remaining if via)
        if not direct and not transfer:
            continue
        try:
            delay_min = max(0, int(float(item.get("SEC_LATE") or 0)) // 60)
        except (TypeError, ValueError):
            delay_min = 0
        state = classify_status(item.get("STATUS"), delay_min)
        if state == "departed" or departs + timedelta(minutes=delay_min) < now - timedelta(minutes=1):
            continue
        rows.append(
            {
                "train_id": str(item.get("TRAIN_ID") or "").strip(),
                "line": (item.get("LINEABBREVIATION") or item.get("LINE") or "").strip(),
                "destination": (item.get("DESTINATION") or "").strip(),
                "scheduled": iso(departs),
                "departs": iso(departs + timedelta(minutes=delay_min)),
                "delay_min": delay_min,
                "status": (item.get("STATUS") or "").strip() or None,
                "state": state,
                "track": (str(item.get("TRACK") or "").strip() or None),
                "direct": direct,
                "via": None if direct else (via or {}).get("name"),
            }
        )
    rows.sort(key=lambda r: r["departs"])
    return rows[:MAX_DEPARTURES]


class NJTransitIntegration(BaseIntegration):
    name = "transit"
    interval_seconds = 120
    required_env = ["NJT_USERNAME", "NJT_PASSWORD"]

    def __init__(self, settings: Settings, config: DashboardConfig) -> None:
        super().__init__(settings, config)
        self._stations: dict[str, dict[str, str]] | None = None  # lower name -> {code, name}

    # ------------------------------------------------------------------ token
    @property
    def _token_file(self) -> Path:
        return Path(self.settings.data_dir) / "njt_token.json"

    def _read_token_file(self) -> dict[str, Any]:
        try:
            data = json.loads(self._token_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_token_file(self, data: dict[str, Any]) -> None:
        try:
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            self._token_file.write_text(json.dumps(data), encoding="utf-8")
        except OSError as exc:  # the token still works for this process
            log.warning("could not save the NJ Transit token: %s", exc.__class__.__name__)

    async def _post(self, client: httpx.AsyncClient, method: str, **fields: str) -> Any:
        resp = await request(client, "POST", f"{BASE_URL}/{method}", data=fields, retries=1, service="NJ Transit")
        if resp.status_code == 500 and "invalid token" in resp.text.lower():
            raise InvalidToken
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(f"{resp.status_code}", request=resp.request, response=resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise ValueError("NJ Transit returned something that is not JSON") from exc

    async def _new_token(self, client: httpx.AsyncClient, today: str) -> str:
        saved = self._read_token_file()
        created = [d for d in saved.get("created") or [] if d == today]
        if len(created) >= TOKENS_PER_DAY:
            raise TokenLimit(f"NJ Transit allows {TOKENS_PER_DAY} new tokens a day and they are used up; trains return tomorrow")
        body = await self._post(client, "getToken", username=self.settings.njt_username, password=self.settings.njt_password)
        token = str(body.get("UserToken") or "")
        if str(body.get("Authenticated", "")).lower() != "true" or not token:
            raise PermissionError("NJ Transit rejected the username or password; check NJT_USERNAME and NJT_PASSWORD")
        self._write_token_file({"token": token, "created": [*created, today]})
        return token

    async def _token(self, client: httpx.AsyncClient, today: str, renew: bool = False) -> str:
        saved = self._read_token_file()
        token = str(saved.get("token") or "")
        if token and not renew:
            return token
        return await self._new_token(client, today)

    async def _call(self, client: httpx.AsyncClient, method: str, today: str, **fields: str) -> Any:
        """A token carrying call, retried once with a fresh token when the saved one is rejected."""
        token = await self._token(client, today)
        try:
            return await self._post(client, method, token=token, **fields)
        except InvalidToken:
            token = await self._token(client, today, renew=True)
            return await self._post(client, method, token=token, **fields)

    # --------------------------------------------------------------- stations
    async def _station(self, client: httpx.AsyncClient, today: str, wanted: str) -> dict[str, str]:
        """{code, name} for a station given by two letter code or by name (exact, then prefix, then substring)."""
        if self._stations is None:
            body = await self._call(client, "getStationList", today)
            rows = body if isinstance(body, list) else (body.get("STATIONS") or body.get("ITEMS") or []) if isinstance(body, dict) else []
            self._stations = {}
            for row in rows:
                name = (row.get("STATIONNAME") or "").strip()
                code = (row.get("STATION_2CHAR") or "").strip().upper()
                if name and code:
                    self._stations[name.lower()] = {"code": code, "name": name}
        key = wanted.strip().lower()
        if len(key) == 2 and key.upper() in {s["code"] for s in self._stations.values()}:
            return next(s for s in self._stations.values() if s["code"] == key.upper())
        for match in (lambda n: n == key, lambda n: n.startswith(key), lambda n: key in n):
            for name, station in self._stations.items():
                if match(name):
                    return station
        raise ValueError(f"NJ Transit has no station called {wanted!r}; use the name shown on njtransit.com or its two letter code")

    # ------------------------------------------------------------------ fetch
    async def fetch(self) -> dict[str, Any]:
        tz = local_tz()
        now = utcnow().astimezone(tz)
        today = now.date().isoformat()
        async with make_client(timeout=15.0) as client:
            home = await self._station(client, today, self.settings.njt_from)
            away = await self._station(client, today, self.settings.njt_to)
            via = await self._station(client, today, self.settings.njt_via) if self.settings.njt_via else None
            outbound = await self._call(client, "getTrainSchedule", today, station=home["code"])
            inbound = await self._call(client, "getTrainSchedule", today, station=away["code"])
        messages = [str(m.get("MSG_TEXT") or m.get("MSG") or m) for m in (outbound.get("STATIONMSGS") or []) if m] if isinstance(outbound, dict) else []
        return {
            "from": home,
            "to": away,
            "via": via,
            "outbound": direction_rows(outbound.get("ITEMS") or [], home, away, via, now, tz),
            "inbound": direction_rows(inbound.get("ITEMS") or [], away, home, via, now, tz),
            "messages": [m[:200] for m in messages][:3],
            "generated_at": iso(utcnow()),
        }

    def mock(self) -> dict[str, Any]:
        """Fixture departures expressed as minute offsets from now, so the mock board always shows trains ahead."""
        fx = load_fixture("njtransit/departures.json")
        tz = local_tz()
        now = utcnow().astimezone(tz).replace(second=0, microsecond=0)
        stations = {s["name"].lower(): s for s in fx["stations"]}
        home = stations[fx["from"].lower()]
        away = stations[fx["to"].lower()]
        via = stations[fx["via"].lower()]

        def rows(direction: str) -> list[dict[str, Any]]:
            out = []
            for d in fx[direction]:
                scheduled = now + timedelta(minutes=int(d["in_minutes"]))
                delay = int(d.get("delay_min") or 0)
                state = d.get("state") or ("delayed" if delay >= 3 else "on_time")
                out.append(
                    {
                        "train_id": d["train_id"],
                        "line": d["line"],
                        "destination": d["destination"],
                        "scheduled": iso(scheduled),
                        "departs": iso(scheduled + timedelta(minutes=delay)),
                        "delay_min": delay,
                        "status": d.get("status") or ("ON TIME" if state == "on_time" else state.upper()),
                        "state": state,
                        "track": d.get("track"),
                        "direct": bool(d["direct"]),
                        "via": None if d["direct"] else via["name"],
                    }
                )
            return out[:MAX_DEPARTURES]

        return {
            "from": home,
            "to": away,
            "via": via,
            "outbound": rows("outbound"),
            "inbound": rows("inbound"),
            "messages": fx.get("messages") or [],
            "generated_at": iso(utcnow()),
        }
