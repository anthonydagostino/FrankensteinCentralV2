"""Plex Media Server: status, now playing, recently added, on deck, library counts."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

import httpx

from ..util import iso, utcnow
from .base import BaseIntegration, Degraded, describe_error, load_fixture, make_client, request

log = logging.getLogger("frankenstein.plex")

RAILS_TTL = 15 * 60


def plex_headers(token: str, client_id: str) -> dict[str, str]:
    return {
        "X-Plex-Token": token,
        "Accept": "application/json",
        "X-Plex-Product": "FrankensteinCentral",
        "X-Plex-Client-Identifier": client_id,
        "X-Plex-Version": "0.1",
    }


def _episode_label(item: dict) -> str | None:
    if item.get("type") != "episode":
        return None
    season = item.get("parentIndex")
    ep = item.get("index")
    if season is None or ep is None:
        return None
    return f"S{int(season):02d}E{int(ep):02d}"


def _poster(item: dict) -> str | None:
    # Episodes: prefer the show poster; movies: their own thumb
    return item.get("grandparentThumb") or item.get("thumb") or item.get("parentThumb")


def _item(item: dict) -> dict:
    kind = item.get("type")
    title = item.get("title")
    show = item.get("grandparentTitle")
    if kind == "season":
        show = item.get("parentTitle")
    display = show or title
    subtitle = None
    if kind == "episode":
        subtitle = f"{_episode_label(item) or ''} {title}".strip()
    elif kind == "season":
        subtitle = title
    elif kind == "movie":
        subtitle = str(item.get("year")) if item.get("year") else None
    added = item.get("addedAt")
    return {
        "rating_key": str(item.get("ratingKey")),
        "type": kind,
        "title": display,
        "subtitle": subtitle,
        "year": item.get("year"),
        "thumb": _poster(item),
        "added_at": iso(datetime.fromtimestamp(int(added), tz=utcnow().tzinfo)) if added else None,
        "view_offset": item.get("viewOffset"),
        "duration": item.get("duration"),
        "progress": int(round(100 * int(item.get("viewOffset") or 0) / int(item["duration"]))) if item.get("duration") else None,
    }


def parse_sessions(raw: dict) -> list[dict]:
    out = []
    for s in (raw.get("MediaContainer", {}) or {}).get("Metadata", []) or []:
        duration = int(s.get("duration") or 0)
        offset = int(s.get("viewOffset") or 0)
        player = s.get("Player", {}) or {}
        out.append(
            {
                "session_key": s.get("sessionKey"),
                "rating_key": str(s.get("ratingKey")),
                "type": s.get("type"),
                "title": s.get("grandparentTitle") or s.get("title"),
                "subtitle": f"{_episode_label(s) or ''} {s.get('title')}".strip() if s.get("type") == "episode" else (str(s.get("year")) if s.get("year") else None),
                "thumb": _poster(s),
                "user": (s.get("User", {}) or {}).get("title"),
                "player": player.get("title") or player.get("product"),
                "state": player.get("state", "playing"),
                "progress": int(round(100 * offset / duration)) if duration else 0,
                "view_offset": offset,
                "duration": duration,
                "transcoding": "TranscodeSession" in s and bool(s.get("TranscodeSession")),
            }
        )
    return out


def parse_rail(raw: dict, limit: int = 12) -> list[dict]:
    items = (raw.get("MediaContainer", {}) or {}).get("Metadata", []) or []
    return [_item(i) for i in items[:limit]]


def deep_links(public_url: str, machine_id: str | None) -> dict:
    base = public_url.rstrip("/")
    server = f"{base}/#!/media/{machine_id}/com.plexapp.plugins.library" if machine_id else base
    return {"server": server, "item_template": f"{base}/#!/server/{machine_id}/details?key=" + quote("/library/metadata/", safe="") + "{rating_key}" if machine_id else base}


class PlexIntegration(BaseIntegration):
    name = "plex"
    interval_seconds = 30
    required_env = ["PLEX_URL", "PLEX_TOKEN"]

    def __init__(self, settings, config, client_id_provider: Callable[[], str] | None = None):
        super().__init__(settings, config)
        self._client_id_provider = client_id_provider
        self._client_id: str | None = None
        self._rails: tuple[datetime, dict] | None = None

    def client_id(self) -> str:
        if self._client_id:
            return self._client_id
        if self._client_id_provider:
            self._client_id = self._client_id_provider()
        else:
            self._client_id = str(uuid.uuid4())
        return self._client_id

    def headers(self) -> dict[str, str]:
        return plex_headers(self.settings.plex_token, self.client_id())

    async def _get(self, client: httpx.AsyncClient, path: str, **kwargs: Any) -> dict:
        resp = await request(client, "GET", f"{self.settings.plex_url.rstrip('/')}{path}", service="Plex", **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def _fetch_rails(self, client: httpx.AsyncClient) -> dict:
        now = utcnow()
        if self._rails and (now - self._rails[0]).total_seconds() < RAILS_TTL:
            return self._rails[1]
        rails: dict = {"recently_added": [], "on_deck": [], "libraries": []}
        errors = []
        try:
            rails["recently_added"] = parse_rail(await self._get(client, "/library/recentlyAdded", headers={"X-Plex-Container-Start": "0", "X-Plex-Container-Size": "12"}))
        except Exception as exc:
            errors.append(f"recently added: {describe_error(exc, 'Plex')}")
        try:
            rails["on_deck"] = parse_rail(await self._get(client, "/library/onDeck"))
        except Exception as exc:
            errors.append(f"on deck: {describe_error(exc, 'Plex')}")
        try:
            sections = (await self._get(client, "/library/sections")).get("MediaContainer", {}).get("Directory", []) or []
            libs = []
            for sec in sections:
                count = None
                try:
                    payload = await self._get(client, f"/library/sections/{sec.get('key')}/all", headers={"X-Plex-Container-Start": "0", "X-Plex-Container-Size": "0"})
                    count = (payload.get("MediaContainer", {}) or {}).get("totalSize")
                except Exception:
                    pass
                libs.append({"key": sec.get("key"), "title": sec.get("title"), "type": sec.get("type"), "count": count})
            rails["libraries"] = libs
        except Exception as exc:
            errors.append(f"libraries: {describe_error(exc, 'Plex')}")
        rails["errors"] = errors
        self._rails = (now, rails)
        return rails

    async def fetch(self) -> dict:
        async with make_client(headers=self.headers()) as client:
            identity = (await self._get(client, "/identity")).get("MediaContainer", {}) or {}
            machine_id = identity.get("machineIdentifier")
            version = identity.get("version")
            sessions = parse_sessions(await self._get(client, "/status/sessions"))
            rails = await self._fetch_rails(client)
        data = {
            "server": {"online": True, "version": version, "machine_id": machine_id, "name": identity.get("friendlyName")},
            "sessions": sessions,
            "recently_added": rails["recently_added"],
            "on_deck": rails["on_deck"],
            "libraries": rails["libraries"],
            "links": deep_links(self.settings.plex_public_url, machine_id),
        }
        if rails.get("errors"):
            raise Degraded(data, "; ".join(rails["errors"]))
        return data

    def mock(self) -> dict:
        identity = load_fixture("plex/identity.json")["MediaContainer"]
        sessions = parse_sessions(load_fixture("plex/sessions.json"))
        recently = parse_rail(load_fixture("plex/recently_added.json"))
        on_deck = parse_rail(load_fixture("plex/on_deck.json"))
        sections = load_fixture("plex/sections.json")["MediaContainer"]["Directory"]
        counts = load_fixture("plex/section_counts.json")
        libraries = [{"key": s["key"], "title": s["title"], "type": s["type"], "count": counts.get(str(s["key"]))} for s in sections]
        return {
            "server": {"online": True, "version": identity["version"], "machine_id": identity["machineIdentifier"], "name": "optiplex-plex"},
            "sessions": sessions,
            "recently_added": recently,
            "on_deck": on_deck,
            "libraries": libraries,
            "links": deep_links(self.settings.plex_public_url or "https://app.plex.tv/desktop", identity["machineIdentifier"]),
        }
