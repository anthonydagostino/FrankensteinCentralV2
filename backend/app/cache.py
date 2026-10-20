"""In-memory module cache mirrored to SQLite, plus the standard response envelope."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .db import Database
from .logsetup import redact_text
from .util import dumps, iso, parse_iso, utcnow

log = logging.getLogger("frankenstein.cache")

STALE_MULTIPLIER = 3


@dataclass
class Entry:
    module: str
    data: Any = None
    fetched_at: datetime | None = None
    status: str = "error"
    error: str | None = "First refresh has not completed yet"
    configured: bool = True
    interval: int = 300
    last_attempt: datetime | None = None
    attempts_failed: int = 0
    hint: list[str] = field(default_factory=list)


class Cache:
    def __init__(self, db: Database | None = None):
        self.db = db
        self._entries: dict[str, Entry] = {}
        if db is not None:
            self._load()

    # -- persistence -----------------------------------------------------
    def _load(self) -> None:
        assert self.db is not None
        for row in self.db.fetchall("SELECT key, payload, fetched_at, status, error FROM cache"):
            try:
                data = json.loads(row["payload"]) if row["payload"] else None
            except json.JSONDecodeError:
                data = None
            self._entries[row["key"]] = Entry(
                module=row["key"],
                data=data,
                fetched_at=parse_iso(row["fetched_at"]),
                status=row["status"] or "error",
                error=row["error"],
            )
        if self._entries:
            log.info("restored %d cached modules from SQLite", len(self._entries))

    def _persist(self, entry: Entry) -> None:
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO cache(key, payload, fetched_at, status, error) VALUES(?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, fetched_at=excluded.fetched_at, status=excluded.status, error=excluded.error",
                (entry.module, dumps(entry.data), iso(entry.fetched_at), entry.status, entry.error),
            )
        except Exception as exc:  # never let persistence break a refresh
            log.warning("could not persist cache for %s: %s", entry.module, exc)

    # -- writes ----------------------------------------------------------
    def _entry(self, module: str) -> Entry:
        if module not in self._entries:
            self._entries[module] = Entry(module=module)
        return self._entries[module]

    def configure(self, module: str, interval: int, configured: bool, hint: list[str] | None = None) -> None:
        e = self._entry(module)
        e.interval = interval
        e.configured = configured
        e.hint = hint or []
        if not configured:
            e.status = "disabled"
            e.error = None

    def set_ok(self, module: str, data: Any) -> None:
        e = self._entry(module)
        e.data = json.loads(dumps(data))
        e.fetched_at = utcnow()
        e.last_attempt = e.fetched_at
        e.status = "ok"
        e.error = None
        e.attempts_failed = 0
        self._persist(e)

    def set_degraded(self, module: str, data: Any, error: str) -> None:
        e = self._entry(module)
        e.data = json.loads(dumps(data))
        e.fetched_at = utcnow()
        e.last_attempt = e.fetched_at
        e.status = "degraded"
        e.error = redact_text(error)[:300]
        e.attempts_failed = 0
        self._persist(e)

    def set_error(self, module: str, error: str) -> None:
        e = self._entry(module)
        e.last_attempt = utcnow()
        e.status = "error"
        e.error = redact_text(error)[:300]
        e.attempts_failed += 1
        self._persist(e)

    def set_disabled(self, module: str, hint: list[str]) -> None:
        e = self._entry(module)
        e.configured = False
        e.hint = hint
        e.status = "disabled"
        e.error = None
        e.last_attempt = utcnow()

    # -- reads -----------------------------------------------------------
    def get(self, module: str) -> Entry | None:
        return self._entries.get(module)

    def data(self, module: str) -> Any:
        e = self._entries.get(module)
        return e.data if e else None

    def is_stale(self, module: str) -> bool:
        e = self._entries.get(module)
        if e is None or e.fetched_at is None:
            return False
        if e.status == "disabled":
            return False
        age = (utcnow() - e.fetched_at).total_seconds()
        return age > STALE_MULTIPLIER * max(e.interval, 1)

    def envelope(self, module: str, data: Any = None, *, override_data: bool = False) -> dict:
        e = self._entries.get(module)
        if e is None:
            return {
                "module": module,
                "status": "error",
                "configured": True,
                "fetched_at": None,
                "stale": False,
                "error": "First refresh has not completed yet",
                "data": None,
            }
        payload = data if override_data else e.data
        status = e.status
        error = e.error
        if status == "error" and e.data is not None and e.fetched_at is not None:
            # keep serving last good data; the error is informative
            pass
        return {
            "module": module,
            "status": status,
            "configured": e.configured,
            "fetched_at": iso(e.fetched_at),
            "stale": self.is_stale(module),
            "error": error,
            "data": payload,
            "setup_hint": e.hint if status == "disabled" else None,
        }

    def all_status(self) -> list[dict]:
        out = []
        for e in self._entries.values():
            out.append(
                {
                    "module": e.module,
                    "status": e.status,
                    "configured": e.configured,
                    "fetched_at": iso(e.fetched_at),
                    "last_attempt": iso(e.last_attempt),
                    "stale": self.is_stale(e.module),
                    "error": e.error,
                    "interval": e.interval,
                }
            )
        return out
