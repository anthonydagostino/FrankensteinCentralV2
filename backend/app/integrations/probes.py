"""Generic HTTP health probes configured in dashboard.yaml."""

from __future__ import annotations

import asyncio
import time

from ..util import iso, utcnow
from .base import BaseIntegration, describe_error, make_client


class ProbesIntegration(BaseIntegration):
    name = "probes"
    interval_seconds = 60

    def _targets(self) -> list[dict]:
        out = []
        for p in self.config.probes:
            base = self.settings.env_value(p.url_env) or getattr(self.settings, p.url_env.lower(), "")
            if not base:
                continue
            headers = {}
            if p.auth == "firefly" and self.settings.firefly_token:
                headers["Authorization"] = f"Bearer {self.settings.firefly_token}"
                headers["Accept"] = "application/json"
            if p.auth == "plex" and self.settings.plex_token:
                headers["X-Plex-Token"] = self.settings.plex_token
            out.append({"name": p.name, "url": base.rstrip("/") + p.path, "expect": p.expect, "headers": headers, "base": base.rstrip("/")})
        return out

    def is_configured(self) -> bool:
        return bool(self._targets())

    def setup_hint(self) -> list[str]:
        return [p.url_env for p in self.config.probes]

    async def _probe(self, client, target: dict) -> dict:
        started = time.perf_counter()
        try:
            resp = await client.get(target["url"], headers=target["headers"])
            latency = int((time.perf_counter() - started) * 1000)
            ok = resp.status_code == target["expect"]
            return {"name": target["name"], "url": target["base"], "ok": ok, "status_code": resp.status_code, "latency_ms": latency, "error": None if ok else f"HTTP {resp.status_code}"}
        except Exception as exc:
            return {"name": target["name"], "url": target["base"], "ok": False, "status_code": None, "latency_ms": None, "error": describe_error(exc, target["name"])}

    async def fetch(self) -> dict:
        async with make_client(timeout=8.0) as client:
            results = await asyncio.gather(*(self._probe(client, t) for t in self._targets()))
        return {"probes": list(results), "checked_at": iso(utcnow())}

    def mock(self) -> dict:
        names = [p.name for p in self.config.probes] or ["Firefly III", "Vaultwarden", "Plex"]
        latencies = [41, 12, 27, 33]
        return {
            "probes": [{"name": n, "url": None, "ok": True, "status_code": 200, "latency_ms": latencies[i % len(latencies)], "error": None} for i, n in enumerate(names)],
            "checked_at": iso(utcnow()),
        }
