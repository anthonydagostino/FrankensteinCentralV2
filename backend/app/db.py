"""Tiny SQLite layer. One connection, one lock, plain SQL."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY,
  payload TEXT,
  fetched_at TEXT,
  status TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS benefit_overrides (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  firefly_journal_id INTEGER UNIQUE NOT NULL,
  classification TEXT NOT NULL,
  benefit_id TEXT,
  period_key TEXT,
  note TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS benefit_manual_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  benefit_id TEXT NOT NULL,
  period_key TEXT NOT NULL,
  amount TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(benefit_id, period_key)
);
CREATE TABLE IF NOT EXISTS benefit_snapshots (
  benefit_id TEXT NOT NULL,
  period_key TEXT NOT NULL,
  cap TEXT, used TEXT, pending TEXT, remaining TEXT,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (benefit_id, period_key)
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            with contextlib.suppress(sqlite3.DatabaseError):
                self._conn.execute("PRAGMA journal_mode=WAL")
                # WAL keeps NORMAL crash safe (a power loss can lose the last commits, never corrupt), and it drops
                # the per-statement fsync that otherwise runs on the event loop for every cache write
                self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            self._migrate()

    def _migrate(self) -> None:
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(cache)").fetchall()}
        if "source" not in cols:
            self._conn.execute("ALTER TABLE cache ADD COLUMN source TEXT")
            self._conn.commit()

    # ---- generic helpers
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        """Run one statement for many parameter rows in a single transaction."""
        with self._lock:
            self._conn.executemany(sql, [tuple(r) for r in rows])
            self._conn.commit()

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    # ---- settings
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """One value from the settings table, or `default`."""
        row = self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Upsert one settings row."""
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def all_settings(self) -> dict[str, str]:
        """Every settings row as a dict."""
        return {r["key"]: r["value"] for r in self.fetchall("SELECT key, value FROM settings")}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
