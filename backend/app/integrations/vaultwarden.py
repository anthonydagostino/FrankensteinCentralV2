"""Vaultwarden health: /alive, /api/version, optional backup freshness."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from ..util import iso, utcnow
from .base import BaseIntegration, describe_error, make_client, request

log = logging.getLogger("frankenstein.vault")


def backup_status(directory: str) -> dict | None:
    if not directory:
        return None
    path = Path(directory)
    if not path.exists():
        return {"available": False, "error": "backup directory not found"}
    newest: tuple[float, str] | None = None
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                full = Path(root) / f
                try:
                    mtime = full.stat().st_mtime
                except OSError:
                    continue
                if newest is None or mtime > newest[0]:
                    newest = (mtime, str(full.relative_to(path)))
    except OSError as exc:
        return {"available": False, "error": str(exc)}
    if newest is None:
        return {"available": True, "newest_file": None, "age_hours": None}
    age_hours = (time.time() - newest[0]) / 3600
    return {"available": True, "newest_file": newest[1], "age_hours": round(age_hours, 1)}


class VaultwardenIntegration(BaseIntegration):
    name = "vault"
    interval_seconds = 60
    required_env = ["VAULTWARDEN_URL"]

    def _public(self) -> dict:
        public = self.settings.vaultwarden_public_url.rstrip("/")
        return {"public_url": public or None, "admin_url": f"{public}/admin" if public else None}

    async def fetch(self) -> dict:
        base = self.settings.vaultwarden_url.rstrip("/")
        online = False
        latency_ms = None
        version = None
        error = None
        async with make_client(timeout=8.0) as client:
            started = time.perf_counter()
            try:
                resp = await request(client, "GET", f"{base}/alive", retries=1, service="Vaultwarden")
                latency_ms = int((time.perf_counter() - started) * 1000)
                online = resp.status_code == 200
                if not online:
                    error = f"/alive returned HTTP {resp.status_code}"
            except Exception as exc:
                error = describe_error(exc, "Vaultwarden")
            try:
                vresp = await client.get(f"{base}/api/version")
                if vresp.status_code == 200:
                    text = vresp.text.strip().strip('"')
                    version = text[:40]
            except Exception:
                version = None
        return {
            "online": online,
            "latency_ms": latency_ms,
            "version": version,
            "error": error,
            "checked_at": iso(utcnow()),
            "backup": backup_status(self.settings.vaultwarden_backup_dir),
            **self._public(),
        }

    def mock(self) -> dict:
        return {
            "online": True,
            "latency_ms": 38,
            "version": "1.33.2",
            "error": None,
            "checked_at": iso(utcnow()),
            "backup": {"available": True, "newest_file": "db-20261020-0300.sqlite3.gz", "age_hours": 6.4},
            "public_url": self.settings.vaultwarden_public_url or "https://vault.example.ts.net",
            "admin_url": (self.settings.vaultwarden_public_url or "https://vault.example.ts.net").rstrip("/") + "/admin",
        }
