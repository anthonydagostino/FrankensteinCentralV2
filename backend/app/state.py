"""Shared application state: settings, config, db, cache, scheduler, engine, derived views."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from .auth import password_configured
from .cache import Cache
from .config_loader import BenefitsCatalog, DashboardConfig
from .db import Database
from .scheduler import Scheduler
from .services.attention import build_attention
from .services.benefits.engine import BenefitsEngine, strip_internal
from .services.cards import card_metrics, resolve_card_accounts
from .services.finance import build_summary, firefly_links
from .services.recurring import detect as detect_recurring
from .settings import Settings
from .util import iso, local_now, money, today_local, utcnow

MEMO_SLOTS = 16  # benefits per year plus finance, recurring, cards: cleared wholesale if a client asks for many years

log = logging.getLogger("frankenstein.state")


class AppState:
    """Everything a request handler needs, built once at startup and stored on app.state.fc.

    Views derived from the Firefly cache (finance summary, cards, benefits, recurring charges) are
    computed on demand and memoized until the next Firefly refresh, override change, or day change,
    so the continuously polled routes (/api/attention, /api/finance/summary) cost O(1) after the first call.
    """

    def __init__(self, settings: Settings, config: DashboardConfig, catalog: BenefitsCatalog, db: Database, cache: Cache):
        self.settings = settings
        self.config = config
        self.catalog = catalog
        self.db = db
        self.cache = cache
        self.scheduler = Scheduler(cache)
        self.engine = BenefitsEngine(catalog, config.cards)
        self.integrations: dict[str, Any] = {}
        self._memo: dict[str, tuple[tuple, Any]] = {}  # view name -> (key it was computed for, value)
        self._overrides_version = 0  # bumped whenever overrides, manual usage, or UI settings change
        self.background_tasks: set[asyncio.Task] = set()  # keeps fire-and-forget tasks alive until done

    def spawn(self, coro) -> None:
        """Run a coroutine in the background without losing the task reference."""
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    def derived_envelope(self, module: str, builder: Callable[[], Any]) -> dict:
        """Envelope for a view computed from the Firefly cache: same status and freshness as Firefly,
        the module name of the view, and a clear error (never a 500) if the derivation itself fails."""
        env = self.cache.envelope("firefly")
        env["module"] = module
        if env["data"] is not None:
            try:
                env["data"] = builder()
            except Exception as exc:
                log.exception("%s view failed", module)
                env["status"] = "error"
                env["error"] = f"Could not compute {module}: {exc.__class__.__name__}"
                env["data"] = None
        return env

    # ---- firefly derived
    def firefly_data(self) -> dict | None:
        return self.cache.data("firefly")

    def card_accounts(self) -> dict[str, dict | None]:
        """Firefly account per configured card id (None when unresolved), honoring pins saved in settings."""
        data = self.firefly_data() or {}
        return resolve_card_accounts(self.config.cards, data.get("accounts") or [], self.db)

    def overrides(self) -> dict[int, dict]:
        rows = self.db.fetchall("SELECT * FROM benefit_overrides")
        return {int(r["firefly_journal_id"]): dict(r) for r in rows}

    def manual_usage(self) -> dict[str, dict[str, Decimal]]:
        out: dict[str, dict[str, Decimal]] = {}
        for r in self.db.fetchall("SELECT benefit_id, period_key, amount FROM benefit_manual_usage"):
            out.setdefault(r["benefit_id"], {})[r["period_key"]] = money(r["amount"])
        return out

    def invalidate_benefits(self) -> None:
        """Call after anything that changes a derived view's input other than Firefly data itself."""
        self._overrides_version += 1
        self._memo.clear()

    def _firefly_key(self) -> tuple:
        """Memo key shared by every Firefly derived view: it changes on refresh, override edits, and at midnight."""
        entry = self.cache.get("firefly")
        return (iso(entry.fetched_at) if entry else None, self._overrides_version, today_local().isoformat())

    def _memoized(self, name: str, key: tuple, builder: Callable[[], Any]) -> Any:
        hit = self._memo.get(name)
        if hit is not None and hit[0] == key:
            return hit[1]
        if len(self._memo) >= MEMO_SLOTS:
            self._memo.clear()
        value = builder()
        self._memo[name] = (key, value)
        return value

    def benefits(self, year: int | None = None) -> dict | None:
        """Engine result for the year, memoized per year on the Firefly key."""
        data = self.firefly_data()
        if data is None:
            return None
        today = today_local()
        year = year or today.year
        return self._memoized(
            f"benefits:{year}",
            self._firefly_key(),
            lambda: self.engine.compute(data.get("transactions") or [], self.card_accounts(), self.overrides(), self.manual_usage(), today, year),
        )

    def benefits_public(self, year: int | None = None) -> dict | None:
        """The benefits view without the internal classification rows."""
        result = self.benefits(year)
        return strip_internal(result) if result else None

    def finance_summary(self) -> dict | None:
        """Finance summary view, memoized to the minute (freshness hours are reported to one decimal)."""
        data = self.firefly_data()
        if data is None:
            return None
        now = local_now()
        return self._memoized(
            "finance",
            (*self._firefly_key(), now.strftime("%H:%M")),
            lambda: build_summary(data, self.config, self.settings.firefly_vanity_url, now.date(), now),
        )

    def recurring_ignored(self) -> set[str]:
        raw = self.db.get_setting("recurring_ignore") or ""
        return {k for k in raw.split("\n") if k}

    def set_recurring_ignored(self, key: str, ignore: bool) -> set[str]:
        keys = self.recurring_ignored()
        if ignore:
            keys.add(key)
        else:
            keys.discard(key)
        self.db.set_setting("recurring_ignore", "\n".join(sorted(keys)))
        self.invalidate_benefits()
        return keys

    def recurring(self) -> dict | None:
        """Recurring charge detector output, memoized on the Firefly key (the ignore list bumps the key)."""
        data = self.firefly_data()
        if data is None:
            return None
        return self._memoized(
            "recurring",
            self._firefly_key(),
            lambda: detect_recurring(data.get("transactions") or [], today_local(), self.recurring_ignored(), firefly_links(self.settings.firefly_vanity_url)),
        )

    def cards(self) -> dict | None:
        """Card balances, limits, and benefit totals for the cards widget."""
        data = self.firefly_data()
        if data is None:
            return None
        benefits = self.benefits() or {}
        by_card = {c["card"]: c for c in benefits.get("cards", [])}
        classified = benefits.get("_classified", {})
        accounts = self.card_accounts()
        links = firefly_links(self.settings.firefly_vanity_url)
        today = today_local()
        return {
            "cards": [
                card_metrics(
                    card,
                    accounts.get(card.id),
                    data.get("accounts") or [],
                    data.get("transactions") or [],
                    classified.get(card.id, []),
                    by_card.get(card.id),
                    today,
                    links,
                )
                for card in self.config.cards
            ]
        }

    def attention(self, location: str | None = None) -> list[dict]:
        """Items for the attention strip, built only from cached data so it never calls out."""
        benefits = None
        finance = None
        try:
            benefits = self.benefits_public()
        except Exception as exc:  # never break the strip
            log.warning("benefits for attention failed: %s", exc)
        try:
            finance = self.finance_summary()
        except Exception as exc:
            log.warning("finance for attention failed: %s", exc)
        recurring = None
        try:
            recurring = self.recurring()
        except Exception as exc:
            log.warning("recurring for attention failed: %s", exc)
        return build_attention(self.cache, benefits, finance, utcnow(), location, recurring)

    def snapshot_benefits(self) -> None:
        """Upsert one row per benefit per period for history."""
        try:
            result = self.benefits()
        except Exception as exc:
            log.warning("benefit snapshot failed: %s", exc)
            return
        if not result:
            return
        now = iso(utcnow())
        rows = [
            (b["id"], r["period_key"], r["cap"], r["used"], r["pending"], r["remaining"], now)
            for card in result.get("cards", [])
            for b in card.get("benefits", [])
            for r in ([b["current"]] if b.get("current") else []) + list(b.get("history") or [])
        ]
        self.db.executemany(
            "INSERT INTO benefit_snapshots(benefit_id, period_key, cap, used, pending, remaining, computed_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(benefit_id, period_key) DO UPDATE SET cap=excluded.cap, used=excluded.used, pending=excluded.pending, remaining=excluded.remaining, computed_at=excluded.computed_at",
            rows,
        )

    def plex_client_id(self) -> str:
        """Stable X-Plex-Client-Identifier, generated once and kept in the settings table."""
        existing = self.db.get_setting("plex_client_id")
        if existing:
            return existing
        value = str(uuid.uuid4())
        self.db.set_setting("plex_client_id", value)
        return value

    def public_config(self) -> dict:
        """Non-secret configuration for the browser: owner, timezone, locations, link tiles, cards, UI and privacy settings."""
        links = []
        for tile in self.config.links:
            url = self.settings.url_from_env(tile.env_url)
            if url:
                links.append({"name": tile.name, "url": url, "icon": tile.icon})
        ui_settings = self.db.all_settings()
        return {
            "owner_name": self.config.owner_name,
            "timezone": self.config.timezone,
            "locations": [{"name": loc.name, "default": loc.default} for loc in self.config.weather.locations],
            "selected_location": ui_settings.get("weather_location") or self.config.weather.default_location.name,
            "units": self.config.weather.units,
            "links": links,
            "cards": [{"id": c.id, "label": c.label} for c in self.config.cards],
            "ui": {"theme": self.config.ui.theme, "accent": self.config.ui.accent, "kiosk_rotate_seconds": self.config.ui.kiosk_rotate_seconds},
            "privacy": {
                "hide_amounts_by_default": ui_settings.get("privacy_blur", str(self.config.finance.hide_amounts_by_default).lower()) == "true",
                "kiosk_hide_amounts": self.config.finance.kiosk_hide_amounts,
            },
            "features": {
                "finance_sync": bool(self.settings.firefly_importer_url and self.settings.firefly_importer_secret),
                "docker_restart": bool(self.settings.docker_allow_restart),
                "writeback_tags": bool(self.settings.firefly_writeback_tags),
                "kiosk": bool(self.settings.kiosk_token),
                "mock_mode": self.settings.mock_mode,
            },
            "auth": {"password_configured": password_configured(self.settings)},
            "catalog_last_verified": self.catalog.last_verified.isoformat(),
            "currency": self.config.finance.currency,
        }
