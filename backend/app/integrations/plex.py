"""Plex Media Server: status, now playing, recently added, on deck, library counts.

Two ways to reach a server:
  * PLEX_URL set: talk to that address directly with the account token.
  * PLEX_URL empty: ask plex.tv which servers the account can see (owned or shared), pick one,
    use the server specific access token plex.tv hands out for shared servers, and try the
    server's connections in order (public address, local address, relay) until one answers.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

import httpx

from ..util import iso, utcnow
from .base import BaseIntegration, Degraded, TokenRejected, describe_error, load_fixture, make_client, request

log = logging.getLogger("frankenstein.plex")

RAILS_TTL = 15 * 60
DISCOVERY_TTL = 60 * 60
PLEX_TV_RESOURCES = "https://plex.tv/api/v2/resources"
CONNECT_TIMEOUT = 6.0


def plex_headers(token: str, client_id: str) -> dict[str, str]:
    return {
        "X-Plex-Token": token,
        "Accept": "application/json",
        "X-Plex-Product": "FrankensteinCentral",
        "X-Plex-Client-Identifier": client_id,
        "X-Plex-Version": "0.1",
        "X-Plex-Platform": "Linux",
        "X-Plex-Device-Name": "FrankensteinCentral",
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


# --------------------------------------------------------------------------
# plex.tv discovery
# --------------------------------------------------------------------------
def pick_server(resources: list[dict], preferred_name: str = "") -> dict | None:
    servers = [r for r in resources if "server" in str(r.get("provides", ""))]
    if not servers:
        return None
    if preferred_name:
        for r in servers:
            if str(r.get("name", "")).strip().lower() == preferred_name.strip().lower():
                return r
    owned = [r for r in servers if r.get("owned")]
    present = [r for r in servers if r.get("presence")]
    return (owned or present or servers)[0]


def ordered_connections(resource: dict) -> list[str]:
    """Candidate base URLs: public first, then local, then relay. Each connection yields its plex.direct uri and a raw address form."""
    conns = list(resource.get("connections") or [])

    def rank(c: dict) -> tuple[int, int]:
        return (1 if c.get("relay") else 0, 1 if c.get("local") else 0)

    urls: list[str] = []
    for c in sorted(conns, key=rank):
        uri = c.get("uri")
        if uri and uri not in urls:
            urls.append(uri)
        if not c.get("relay") and c.get("address") and c.get("port"):
            raw = f"{c.get('protocol') or 'http'}://{c['address']}:{c['port']}"
            if raw not in urls:
                urls.append(raw)
    return urls


class PlexIntegration(BaseIntegration):
    name = "plex"
    interval_seconds = 30
    required_env = ["PLEX_TOKEN"]

    def __init__(self, settings, config, client_id_provider: Callable[[], str] | None = None):
        super().__init__(settings, config)
        self._client_id_provider = client_id_provider
        self._client_id: str | None = None
        self._rails: tuple[datetime, dict] | None = None
        # resolved connection: (when, base url, server token, server meta)
        self._resolved: tuple[datetime, str, str, dict] | None = None

    # -- identity --------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self.settings.plex_token)

    def setup_hint(self) -> list[str]:
        return ["PLEX_TOKEN", "PLEX_URL (optional, discovered through plex.tv when empty)"]

    def client_id(self) -> str:
        if self._client_id:
            return self._client_id
        if self._client_id_provider:
            self._client_id = self._client_id_provider()
        else:
            self._client_id = str(uuid.uuid4())
        return self._client_id

    def base_url(self) -> str | None:
        if self.settings.plex_url:
            return self.settings.plex_url.rstrip("/")
        return self._resolved[1] if self._resolved else None

    def server_token(self) -> str:
        if self.settings.plex_url or not self._resolved:
            return self.settings.plex_token
        return self._resolved[2]

    def headers(self) -> dict[str, str]:
        return plex_headers(self.server_token(), self.client_id())

    def server_meta(self) -> dict:
        return self._resolved[3] if self._resolved else {}

    # -- discovery -------------------------------------------------------
    async def _discover(self, client: httpx.AsyncClient) -> tuple[str, str, dict]:
        headers = plex_headers(self.settings.plex_token, self.client_id())
        resp = await request(client, "GET", PLEX_TV_RESOURCES, params={"includeHttps": 1, "includeRelay": 1}, headers=headers, service="plex.tv")
        resp.raise_for_status()
        resources = resp.json()
        server = pick_server(resources if isinstance(resources, list) else [], self.settings.plex_server_name)
        if server is None:
            raise RuntimeError("plex.tv lists no server for this account (own one or ask for a share)")
        token = server.get("accessToken") or self.settings.plex_token
        meta = {"name": server.get("name"), "owned": bool(server.get("owned")), "shared_by": server.get("sourceTitle") if not server.get("owned") else None, "machine_id": server.get("clientIdentifier"), "platform": server.get("platform")}
        tried: list[str] = []
        for base in ordered_connections(server):
            try:
                r = await client.get(f"{base}/identity", headers=plex_headers(token, self.client_id()), timeout=CONNECT_TIMEOUT)
                if r.status_code == 200:
                    meta["via"] = "relay" if ".plex.direct" in base and any(c.get("relay") and c.get("uri") == base for c in server.get("connections") or []) else "direct"
                    log.info("Plex server %s reachable (%s)", meta["name"], meta["via"])
                    return base, token, meta
                if r.status_code in (401, 403):
                    raise TokenRejected("Plex: token rejected for this server, regenerate it and update .env")
                tried.append(f"{base} (HTTP {r.status_code})")
            except TokenRejected:
                raise
            except Exception as exc:
                tried.append(f"{base} ({exc.__class__.__name__})")
        raise RuntimeError(f"Plex server {meta['name']} not reachable on any of its {len(tried)} connections")

    async def _ensure_connection(self, client: httpx.AsyncClient) -> tuple[str, str]:
        if self.settings.plex_url:
            return self.settings.plex_url.rstrip("/"), self.settings.plex_token
        now = utcnow()
        if self._resolved and (now - self._resolved[0]).total_seconds() < DISCOVERY_TTL:
            return self._resolved[1], self._resolved[2]
        base, token, meta = await self._discover(client)
        self._resolved = (now, base, token, meta)
        return base, token

    # -- calls -----------------------------------------------------------
    async def _get(self, client: httpx.AsyncClient, base: str, token: str, path: str, **kwargs: Any) -> dict:
        headers = {**plex_headers(token, self.client_id()), **kwargs.pop("headers", {})}
        resp = await request(client, "GET", f"{base}{path}", headers=headers, service="Plex", **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def _fetch_rails(self, client: httpx.AsyncClient, base: str, token: str) -> dict:
        now = utcnow()
        if self._rails and (now - self._rails[0]).total_seconds() < RAILS_TTL:
            return self._rails[1]
        rails: dict = {"recently_added": [], "on_deck": [], "libraries": []}
        errors = []
        try:
            rails["recently_added"] = parse_rail(await self._get(client, base, token, "/library/recentlyAdded", headers={"X-Plex-Container-Start": "0", "X-Plex-Container-Size": "12"}))
        except Exception as exc:
            errors.append(f"recently added: {describe_error(exc, 'Plex')}")
        try:
            rails["on_deck"] = parse_rail(await self._get(client, base, token, "/library/onDeck"))
        except Exception as exc:
            errors.append(f"on deck: {describe_error(exc, 'Plex')}")
        try:
            sections = (await self._get(client, base, token, "/library/sections")).get("MediaContainer", {}).get("Directory", []) or []
            libs = []
            for sec in sections:
                count = None
                try:
                    payload = await self._get(client, base, token, f"/library/sections/{sec.get('key')}/all", headers={"X-Plex-Container-Start": "0", "X-Plex-Container-Size": "0"})
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
        async with make_client() as client:
            base, token = await self._ensure_connection(client)
            try:
                identity = (await self._get(client, base, token, "/identity")).get("MediaContainer", {}) or {}
            except Exception:
                # a cached discovery can go stale (new public IP, relay rotated): forget it and let the next pass rediscover
                self._resolved = None
                raise
            machine_id = identity.get("machineIdentifier") or self.server_meta().get("machine_id")
            version = identity.get("version")
            sessions = parse_sessions(await self._get(client, base, token, "/status/sessions"))
            rails = await self._fetch_rails(client, base, token)
        meta = self.server_meta()
        data = {
            "server": {
                "online": True,
                "version": version,
                "machine_id": machine_id,
                "name": meta.get("name") or identity.get("friendlyName"),
                "owned": meta.get("owned", True if self.settings.plex_url else None),
                "shared_by": meta.get("shared_by"),
                "via": meta.get("via", "direct"),
            },
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
            "server": {"online": True, "version": identity["version"], "machine_id": identity["machineIdentifier"], "name": "Absolute Cinema", "owned": False, "shared_by": "eddiedlugosz", "via": "direct"},
            "sessions": sessions,
            "recently_added": recently,
            "on_deck": on_deck,
            "libraries": libraries,
            "links": deep_links(self.settings.plex_public_url or "https://app.plex.tv/desktop", identity["machineIdentifier"]),
        }
