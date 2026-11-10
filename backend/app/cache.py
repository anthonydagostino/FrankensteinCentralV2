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
    source: str | None = None  # "mock" or "live"


class Cache:
    def __init__(self, db: Database | None = None):
        self.db = db
        self._entries: dict[str, Entry] = {}
        if db is not None:
            self._load()

    # ---- persistence
    def _load(self) -> None:
        if self.db is None:
            return
        for row in self.db.fetchall("SELECT key, payload, fetched_at, status, error, source FROM cache"):
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
                source=row["source"],
            )
        if self._entries:
            log.info("restored %d cached modules from SQLite", len(self._entries))

    def _persist(self, entry: Entry, payload: str | None = None) -> None:
        """Mirror an entry to SQLite. `payload` is the already serialized data when the caller has it."""
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO cache(key, payload, fetched_at, status, error, source) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, fetched_at=excluded.fetched_at, status=excluded.status, error=excluded.error, source=excluded.source",
                (entry.module, payload if payload is not None else dumps(entry.data), iso(entry.fetched_at), entry.status, entry.error, entry.source),
            )
        except Exception as exc:  # never let persistence break a refresh
            log.warning("could not persist cache for %s: %s", entry.module, exc)

    # ---- writes
    def _entry(self, module: str) -> Entry:
        if module not in self._entries:
            self._entries[module] = Entry(module=module)
        return self._entries[module]

    def configure(self, module: str, interval: int, configured: bool, hint: list[str] | None = None, source: str | None = None) -> None:
        """Register a module with its refresh interval, configured flag, setup hint, and data source (mock or live)."""
        e = self._entry(module)
        e.interval = interval
        e.configured = configured
        e.hint = hint or []
        if source and e.source and e.source != source:
            # restored data came from the other mode (mock vs live): never mix them
            log.info("dropping cached %s data from %s mode", module, e.source)
            e.data = None
            e.fetched_at = None
            e.status = "error"
            e.error = "First refresh has not completed yet"
        e.source = source or e.source
        if not configured:
            e.status = "disabled"
            e.error = None
            e.data = None
            e.fetched_at = None

    def _store(self, module: str, data: Any, status: str, error: str | None, source: str | None) -> None:
        """Record a successful (ok or degraded) refresh. Data is serialized once: the JSON text feeds both
        the in-memory copy (so Decimals and dates become plain JSON values) and the SQLite mirror."""
        e = self._entry(module)
        if source:
            e.source = source
        payload = dumps(data)
        e.data = json.loads(payload)
        e.fetched_at = utcnow()
        e.last_attempt = e.fetched_at
        e.status = status
        e.error = redact_text(error)[:300] if error else None
        e.attempts_failed = 0
        self._persist(e, payload)

    def set_ok(self, module: str, data: Any, source: str | None = None) -> None:
        """Store a successful refresh: data replaces the last good payload and the error clears."""
        self._store(module, data, "ok", None, source)

    def set_degraded(self, module: str, data: Any, error: str, source: str | None = None) -> None:
        """Store a partial refresh: the data is kept as last good, the error is shown next to it."""
        self._store(module, data, "degraded", error, source)

    def set_error(self, module: str, error: str) -> None:
        """Record a failed refresh. The last good data stays, so the widget shows it with a stale badge."""
        e = self._entry(module)
        e.last_attempt = utcnow()
        e.status = "error"
        e.error = redact_text(error)[:300]
        e.attempts_failed += 1
        self._persist(e)

    def set_disabled(self, module: str, hint: list[str]) -> None:
        """Mark a module as not configured; its data is dropped and the hint tells the user which env vars to set."""
        e = self._entry(module)
        e.configured = False
        e.hint = hint
        e.status = "disabled"
        e.error = None
        e.data = None
        e.fetched_at = None
        e.last_attempt = utcnow()

    # ---- reads
    def get(self, module: str) -> Entry | None:
        """The raw cache entry for a module, or None if it was never configured."""
        return self._entries.get(module)

    def data(self, module: str) -> Any:
        """The last good payload for a module, or None."""
        e = self._entries.get(module)
        return e.data if e else None

    def is_stale(self, module: str) -> bool:
        """True when the last good payload is older than three times the module's refresh interval (never for disabled modules)."""
        e = self._entries.get(module)
        if e is None or e.fetched_at is None:
            return False
        if e.status == "disabled":
            return False
        age = (utcnow() - e.fetched_at).total_seconds()
        return age > STALE_MULTIPLIER * max(e.interval, 1)

    def envelope(self, module: str) -> dict[str, Any]:
        """The standard response envelope for a module, built from the cached entry."""
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
        # On error the last good data is still served; the error text tells the UI why it is old.
        return {
            "module": module,
            "status": e.status,
            "configured": e.configured,
            "fetched_at": iso(e.fetched_at),
            "stale": self.is_stale(module),
            "error": e.error,
            "data": e.data,
            "setup_hint": e.hint if e.status == "disabled" else None,
        }

    def modules(self) -> list[str]:
        """Names of every configured module."""
        return list(self._entries)

    def all_status(self) -> list[dict[str, Any]]:
        """One status row per module for the Settings page."""
        return [
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
            for e in self._entries.values()
        ]
