"""Shared application state: settings, config, db, cache, scheduler, engine, derived views."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

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

log = logging.getLogger("frankenstein.state")


class AppState:
    def __init__(self, settings: Settings, config: DashboardConfig, catalog: BenefitsCatalog, db: Database, cache: Cache):
        self.settings = settings
        self.config = config
        self.catalog = catalog
        self.db = db
        self.cache = cache
        self.scheduler = Scheduler(cache)
        self.engine = BenefitsEngine(catalog, config.cards)
        self.integrations: dict[str, Any] = {}
        self._benefits_memo: dict[tuple, dict] = {}
        self._overrides_version = 0

    # ---- firefly derived
    def firefly_data(self) -> dict | None:
        return self.cache.data("firefly")

    def card_accounts(self) -> dict[str, dict | None]:
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
        self._overrides_version += 1
        self._benefits_memo.clear()

    def benefits(self, year: int | None = None) -> dict | None:
        data = self.firefly_data()
        if data is None:
            return None
        today = today_local()
        year = year or today.year
        entry = self.cache.get("firefly")
        key = (iso(entry.fetched_at) if entry else None, self._overrides_version, year, today.isoformat(), tuple(sorted(self.db.all_settings().items())))
        memo = self._benefits_memo.get(key)
        if memo is not None:
            return memo
        result = self.engine.compute(data.get("transactions") or [], self.card_accounts(), self.overrides(), self.manual_usage(), today, year)
        self._benefits_memo = {key: result}
        return result

    def benefits_public(self, year: int | None = None) -> dict | None:
        result = self.benefits(year)
        return strip_internal(result) if result else None

    def finance_summary(self) -> dict | None:
        data = self.firefly_data()
        if data is None:
            return None
        return build_summary(data, self.config, self.settings.firefly_vanity_url, today_local(), local_now())

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
        return keys

    def recurring(self) -> dict | None:
        data = self.firefly_data()
        if data is None:
            return None
        return detect_recurring(data.get("transactions") or [], today_local(), self.recurring_ignored(), firefly_links(self.settings.firefly_vanity_url))

    def cards(self) -> dict | None:
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
                card_metrics(card, accounts.get(card.id), data.get("accounts") or [], data.get("transactions") or [], classified.get(card.id, []), by_card.get(card.id), today, links)
                for card in self.config.cards
            ]
        }

    def attention(self, location: str | None = None) -> list[dict]:
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
        for card in result.get("cards", []):
            for b in card.get("benefits", []):
                for r in ([b["current"]] if b.get("current") else []) + list(b.get("history") or []):
                    self.db.execute(
                        "INSERT INTO benefit_snapshots(benefit_id, period_key, cap, used, pending, remaining, computed_at) VALUES(?,?,?,?,?,?,?) "
                        "ON CONFLICT(benefit_id, period_key) DO UPDATE SET cap=excluded.cap, used=excluded.used, pending=excluded.pending, remaining=excluded.remaining, computed_at=excluded.computed_at",
                        (b["id"], r["period_key"], r["cap"], r["used"], r["pending"], r["remaining"], now),
                    )

    def plex_client_id(self) -> str:
        import uuid

        existing = self.db.get_setting("plex_client_id")
        if existing:
            return existing
        value = str(uuid.uuid4())
        self.db.set_setting("plex_client_id", value)
        return value

    def public_config(self) -> dict:
        links = []
        for tile in self.config.links:
            url = self.settings.env_value(tile.env_url) or getattr(self.settings, tile.env_url.lower(), "")
            if url:
                links.append({"name": tile.name, "url": url, "icon": tile.icon})
        ui_settings = self.db.all_settings()
        from .auth import password_configured

        return {
            "owner_name": self.config.owner_name,
            "timezone": self.config.timezone,
            "locations": [{"name": loc.name, "default": loc.default} for loc in self.config.weather.locations],
            "selected_location": ui_settings.get("weather_location") or self.config.weather.default_location.name,
            "units": self.config.weather.units,
            "links": links,
            "cards": [{"id": c.id, "label": c.label} for c in self.config.cards],
            "ui": {"theme": self.config.ui.theme, "accent": self.config.ui.accent, "kiosk_rotate_seconds": self.config.ui.kiosk_rotate_seconds},
            "privacy": {"hide_amounts_by_default": ui_settings.get("privacy_blur", str(self.config.finance.hide_amounts_by_default).lower()) == "true", "kiosk_hide_amounts": self.config.finance.kiosk_hide_amounts},
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
