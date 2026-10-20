"""Docker containers through tecnativa/docker-socket-proxy (read-only by default)."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx

from ..util import iso, utcnow
from .base import BaseIntegration, Degraded, describe_error, load_fixture, make_client, request

log = logging.getLogger("frankenstein.docker")

INSPECT_TTL = 5 * 60
HEALTH_RE = re.compile(r"\((healthy|unhealthy|health: starting)\)", re.I)


def proxy_base(docker_host: str) -> str:
    host = docker_host.strip()
    if host.startswith("tcp://"):
        host = "http://" + host[len("tcp://"):]
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


def parse_health(status: str | None) -> str:
    if not status:
        return "none"
    m = HEALTH_RE.search(status)
    if not m:
        return "none"
    value = m.group(1).lower()
    return "starting" if value.startswith("health:") else value


def _parse_time(value: str | None) -> datetime | None:
    if not value or value.startswith("0001-01-01"):
        return None
    value = value.replace("Z", "+00:00")
    # Docker gives nanoseconds; trim to microseconds
    m = re.match(r"(.*\.\d{6})\d*(.*)", value)
    if m:
        value = m.group(1) + m.group(2)
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None


def build_container(item: dict, inspect: dict | None, previous_restarts: dict[str, int], now: datetime) -> dict:
    cid = item.get("Id", "")
    names = item.get("Names") or []
    name = names[0].lstrip("/") if names else cid[:12]
    labels = item.get("Labels") or {}
    state = item.get("State") or "unknown"
    status = item.get("Status") or ""
    started_at = None
    restart_count = None
    exit_code = None
    if inspect:
        st = inspect.get("State", {}) or {}
        started_at = _parse_time(st.get("StartedAt"))
        restart_count = inspect.get("RestartCount")
        exit_code = st.get("ExitCode")
        if not status and st.get("Status"):
            state = st.get("Status")
        if st.get("Health", {}).get("Status"):
            health = st["Health"]["Status"].lower()
        else:
            health = parse_health(status)
    else:
        health = parse_health(status)
    uptime_seconds = None
    if started_at and state == "running":
        uptime_seconds = int((now - started_at).total_seconds())
    previous = previous_restarts.get(cid)
    return {
        "id": cid,
        "short_id": cid[:12],
        "name": name,
        "display_name": labels.get("frankenstein.name") or name,
        "image": item.get("Image"),
        "state": state,
        "status": status,
        "health": health,
        "uptime_seconds": uptime_seconds,
        "started_at": iso(started_at),
        "restart_count": restart_count,
        "restart_increased": previous is not None and restart_count is not None and restart_count > previous,
        "exit_code": exit_code,
        "url": labels.get("frankenstein.url"),
        "critical": str(labels.get("frankenstein.critical", "")).lower() == "true",
        "hidden": str(labels.get("frankenstein.hide", "")).lower() == "true",
        "project": labels.get("com.docker.compose.project") or None,
        "service": labels.get("com.docker.compose.service"),
        "created": item.get("Created"),
        "ports": [f"{p.get('PublicPort')}:{p.get('PrivatePort')}/{p.get('Type')}" for p in (item.get("Ports") or []) if p.get("PublicPort")],
    }


def group_containers(containers: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for c in containers:
        if c["hidden"]:
            continue
        groups.setdefault(c["project"] or "Standalone", []).append(c)
    out = []
    for project in sorted(groups, key=lambda p: (p == "Standalone", p.lower())):
        items = sorted(groups[project], key=lambda c: c["display_name"].lower())
        out.append({"project": project, "containers": items})
    return out


def summarize(containers: list[dict], info: dict | None) -> dict:
    visible = [c for c in containers if not c["hidden"]]
    return {
        "total": len(visible),
        "running": sum(1 for c in visible if c["state"] == "running"),
        "stopped": sum(1 for c in visible if c["state"] in ("exited", "dead", "created")),
        "paused": sum(1 for c in visible if c["state"] == "paused"),
        "restarting": sum(1 for c in visible if c["state"] == "restarting"),
        "unhealthy": sum(1 for c in visible if c["health"] == "unhealthy"),
        "server_version": (info or {}).get("ServerVersion"),
        "engine_total": (info or {}).get("Containers"),
    }


class DockerIntegration(BaseIntegration):
    name = "docker"
    interval_seconds = 15
    required_env = ["DOCKER_HOST"]

    def __init__(self, settings, config):
        super().__init__(settings, config)
        self._inspect_cache: dict[str, tuple[datetime, dict]] = {}
        self._previous_restarts: dict[str, int] = {}
        self._info: tuple[datetime, dict] | None = None

    async def _inspect(self, client: httpx.AsyncClient, cid: str, now: datetime, sem: asyncio.Semaphore) -> dict | None:
        cached = self._inspect_cache.get(cid)
        if cached and (now - cached[0]).total_seconds() < INSPECT_TTL:
            return cached[1]
        async with sem:
            try:
                resp = await request(client, "GET", f"{self._base()}/containers/{cid}/json", retries=0, service="Docker")
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                log.debug("inspect %s failed: %s", cid[:12], exc)
                return cached[1] if cached else None
        self._inspect_cache[cid] = (now, data)
        return data

    def _base(self) -> str:
        return proxy_base(self.settings.docker_host)

    async def fetch(self) -> dict:
        now = utcnow()
        errors: list[str] = []
        async with make_client(timeout=8.0) as client:
            resp = await request(client, "GET", f"{self._base()}/containers/json", params={"all": "true"}, service="Docker")
            resp.raise_for_status()
            items = resp.json()
            info = None
            if not self._info or (now - self._info[0]).total_seconds() > INSPECT_TTL:
                try:
                    iresp = await request(client, "GET", f"{self._base()}/info", retries=0, service="Docker")
                    iresp.raise_for_status()
                    self._info = (now, iresp.json())
                except Exception as exc:
                    errors.append(f"info: {describe_error(exc, 'Docker')}")
            info = self._info[1] if self._info else None
            sem = asyncio.Semaphore(5)
            inspections = await asyncio.gather(*(self._inspect(client, item.get("Id", ""), now, sem) for item in items))
        containers = [build_container(item, insp, self._previous_restarts, now) for item, insp in zip(items, inspections)]
        for c in containers:
            if c["restart_count"] is not None:
                self._previous_restarts[c["id"]] = c["restart_count"]
        # drop cache entries for containers that no longer exist
        live_ids = {c["id"] for c in containers}
        for cid in list(self._inspect_cache):
            if cid not in live_ids:
                self._inspect_cache.pop(cid, None)
        data = {
            "summary": summarize(containers, info),
            "groups": group_containers(containers),
            "restart_allowed": bool(self.settings.docker_allow_restart),
            "portainer_url": self.settings.portainer_url or None,
            "generated_at": iso(now),
        }
        if errors:
            raise Degraded(data, "; ".join(errors))
        return data

    def mock(self) -> dict:
        now = utcnow()
        items = load_fixture("docker/containers.json")
        inspects = load_fixture("docker/inspect.json")
        info = load_fixture("docker/info.json")
        containers = []
        for item in items:
            insp = inspects.get(item["Id"])
            if insp:
                # keep "started 3 days ago" realistic regardless of today's date
                offset = insp.get("_started_seconds_ago", 0)
                started = now.timestamp() - offset
                insp = dict(insp)
                insp["State"] = dict(insp["State"])
                insp["State"]["StartedAt"] = datetime.fromtimestamp(started, tz=timezone.utc).isoformat()
            containers.append(build_container(item, insp, self._previous_restarts, now))
        for c in containers:
            if c["restart_count"] is not None:
                self._previous_restarts[c["id"]] = c["restart_count"]
        return {
            "summary": summarize(containers, info),
            "groups": group_containers(containers),
            "restart_allowed": bool(self.settings.docker_allow_restart),
            "portainer_url": self.settings.portainer_url or "https://portainer.example.ts.net",
            "generated_at": iso(now),
        }


async def restart_container(settings, cid: str) -> int:
    async with make_client(timeout=30.0) as client:
        resp = await client.post(f"{proxy_base(settings.docker_host)}/containers/{cid}/restart")
    return resp.status_code
