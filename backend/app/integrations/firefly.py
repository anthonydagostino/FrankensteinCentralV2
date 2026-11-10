"""Firefly III: accounts, summary, transactions (split level), insights, budgets, bills."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from ..util import iso, money, today_local, utcnow
from .base import BaseIntegration, Degraded, bearer_headers, describe_error, load_fixture, make_client, request, shift_date

log = logging.getLogger("frankenstein.firefly")

FIREFLY_ACCEPT = "application/vnd.api+json, application/json"
MAX_PAGES = 200  # 100 rows each: a cap of 20,000 rows per listing before the refresh is marked degraded
FIXTURE_ANCHOR = date(2026, 10, 20)


def _dec(value: Any) -> Decimal:
    """Money that tolerates a null or malformed Firefly amount (one bad split must not fail the refresh)."""
    try:
        return money(value)
    except Exception:
        return Decimal("0.00")


def _money_str(value: Any) -> str:
    return f"{_dec(value):.2f}"


def flatten_transactions(groups: list[dict]) -> list[dict]:
    """Flatten Firefly transaction groups into split rows keyed by transaction_journal_id."""
    rows: list[dict] = []
    for group in groups:
        gid = str(group.get("id"))
        attrs = group.get("attributes", {}) or {}
        for split in attrs.get("transactions", []) or []:
            raw_date = str(split.get("date") or "")
            rows.append(
                {
                    "journal_id": int(split.get("transaction_journal_id") or 0),
                    "group_id": gid,
                    "type": split.get("type"),
                    "date": raw_date[:10],
                    "amount": _money_str(split.get("amount")),
                    "description": split.get("description") or "",
                    "source_id": str(split.get("source_id")) if split.get("source_id") is not None else None,
                    "source_name": split.get("source_name") or "",
                    "source_type": split.get("source_type"),
                    "destination_id": str(split.get("destination_id")) if split.get("destination_id") is not None else None,
                    "destination_name": split.get("destination_name") or "",
                    "destination_type": split.get("destination_type"),
                    "category_name": split.get("category_name") or "",
                    "budget_name": split.get("budget_name") or "",
                    "tags": list(split.get("tags") or []),
                    "notes": split.get("notes") or "",
                    "external_id": split.get("external_id"),
                    "currency_code": split.get("currency_code") or "USD",
                }
            )
    rows.sort(key=lambda r: (r["date"], r["journal_id"]))
    return rows


def normalize_accounts(items: list[dict]) -> list[dict]:
    """Active accounts with balances as two decimal strings. credit_limit is Firefly's virtual balance, which this
    dashboard uses as the limit for credit card accounts (Firefly has no dedicated field)."""
    out = []
    for item in items:
        a = item.get("attributes", {}) or {}
        if a.get("active") is False:
            continue
        out.append(
            {
                "id": str(item.get("id")),
                "name": a.get("name") or "",
                "type": a.get("type") or "",
                "role": a.get("account_role") or "",
                "liability_type": a.get("liability_type"),
                "currency": a.get("currency_code") or "USD",
                "balance": _money_str(a.get("current_balance")),
                "balance_date": (a.get("current_balance_date") or "")[:10] or None,
                "credit_limit": _money_str(a.get("virtual_balance")) if a.get("virtual_balance") not in (None, "", "0", "0.0", "0.00", "0.000000") else None,
                "include_net_worth": a.get("include_net_worth", True),
                "notes": a.get("notes") or "",
            }
        )
    return out


def normalize_summary(raw: Any) -> dict:
    """Summary basic returns keys like net-worth-in-USD. Take the first currency variant of each."""
    out: dict[str, str | None] = {"net_worth": None, "spent": None, "earned": None, "bills_unpaid": None, "left_to_spend": None, "currency": None}
    mapping = {
        "net-worth-in-": "net_worth",
        "spent-in-": "spent",
        "earned-in-": "earned",
        "bills-unpaid-in-": "bills_unpaid",
        "left-to-spend-in-": "left_to_spend",
    }
    items = raw.values() if isinstance(raw, dict) else raw
    for item in items:
        key = str(item.get("key", ""))
        for prefix, name in mapping.items():
            if key.startswith(prefix) and out[name] is None:
                value = item.get("monetary_value")
                if value is None:
                    value = item.get("value_parsed")
                out[name] = _money_str(value)
                out["currency"] = out["currency"] or item.get("currency_code")
    return out


def normalize_insight(raw: Any) -> list[dict]:
    """Insight endpoints return a list of {name, difference}; amounts are made positive and sorted descending."""
    out = []
    for item in raw or []:
        amount = _dec(item.get("difference_float", item.get("difference")))
        out.append({"id": str(item.get("id")), "name": item.get("name") or "(none)", "amount": _money_str(abs(amount))})
    out.sort(key=lambda x: Decimal(x["amount"]), reverse=True)
    return out


def normalize_budgets(budgets: list[dict], limits: dict[str, list[dict]]) -> list[dict]:
    """Budgets with this month's limit and spent totals summed over their budget limits."""
    out = []
    for b in budgets:
        a = b.get("attributes", {}) or {}
        if a.get("active") is False:
            continue
        bid = str(b.get("id"))
        limit_total = Decimal("0.00")
        spent_total = Decimal("0.00")
        for lim in limits.get(bid, []):
            la = lim.get("attributes", {}) or {}
            limit_total += _dec(la.get("amount"))
            spent_total += abs(_dec(la.get("spent")))
        if limit_total == 0:
            # Firefly also reports spent on the budget itself for the period
            for s in a.get("spent", []) or []:
                spent_total += abs(_dec(s.get("sum")))
        out.append({"id": bid, "name": a.get("name") or "", "limit": _money_str(limit_total), "spent": _money_str(spent_total)})
    return out


def normalize_bills(raw: list[dict]) -> list[dict]:
    """Active bills (Firefly calls them subscriptions in newer versions) with the next expected date."""
    out = []
    for b in raw:
        a = b.get("attributes", {}) or {}
        if a.get("active") is False:
            continue
        next_dates = a.get("pay_dates") or []
        paid = a.get("paid_dates") or []
        next_expected = a.get("next_expected_match")
        if not next_expected and next_dates:
            next_expected = next_dates[0]
        out.append(
            {
                "id": str(b.get("id")),
                "name": a.get("name") or "",
                "amount_min": _money_str(a.get("amount_min")),
                "amount_max": _money_str(a.get("amount_max")),
                "next_expected": (next_expected or "")[:10] or None,
                "paid_this_period": bool(paid),
                "repeat_freq": a.get("repeat_freq"),
            }
        )
    return out


def window_start(today: date) -> date:
    """Transactions window start: Jan 1 of the current year minus 60 days (spec 8.5.5).

    The window follows the current year only, so a benefits view of an earlier year sees just the
    rows that fall inside it (see DECISIONS.md).
    """
    return date(today.year, 1, 1) - timedelta(days=60)


class Truncated(Exception):
    """A paged listing hit MAX_PAGES; `items` holds the rows fetched so far."""

    def __init__(self, items: list[dict], message: str):
        super().__init__(message)
        self.items = items


class FireflyIntegration(BaseIntegration):
    name = "firefly"
    interval_seconds = 10 * 60
    required_env = ["FIREFLY_URL", "FIREFLY_TOKEN"]

    def __init__(self, settings, config):
        super().__init__(settings, config)
        self._logged_version: str | None = None

    def _base(self) -> str:
        return self.settings.firefly_url.rstrip("/") + "/api/v1"

    async def _get(self, client: httpx.AsyncClient, path: str, **params: Any) -> dict:
        resp = await request(client, "GET", f"{self._base()}{path}", params=params, service="Firefly")
        resp.raise_for_status()
        return resp.json()

    async def _paged(self, client: httpx.AsyncClient, path: str, **params: Any) -> list[dict]:
        """Every page of a listing. Raises Truncated (with the rows so far) past MAX_PAGES."""
        items: list[dict] = []
        page = 1
        while True:
            payload = await self._get(client, path, page=page, limit=100, **params)
            items.extend(payload.get("data", []) or [])
            total_pages = int(((payload.get("meta") or {}).get("pagination") or {}).get("total_pages") or 1)
            if page >= total_pages:
                break
            page += 1
            if page > MAX_PAGES:
                raise Truncated(items, f"{path} truncated at {MAX_PAGES} pages")
        return items

    async def fetch(self) -> dict:
        today = today_local()
        start = window_start(today)
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=40)).replace(day=1) - timedelta(days=1)
        errors: list[str] = []
        async with make_client(timeout=20.0, headers=bearer_headers(self.settings.firefly_token, FIREFLY_ACCEPT)) as client:
            about = await self._get(client, "/about")
            version = (about.get("data") or {}).get("version")
            if version != self._logged_version:
                log.info("Firefly III version %s", version)
                self._logged_version = version

            assets = await self._paged(client, "/accounts", type="asset")
            liabilities = await self._paged(client, "/accounts", type="liabilities")
            accounts = normalize_accounts(assets + liabilities)

            try:
                groups = await self._paged(client, "/transactions", start=start.isoformat(), end=today.isoformat(), type="all")
            except Truncated as exc:
                groups = exc.items
                errors.append(f"transactions: {exc}")
            transactions = flatten_transactions(groups)

            summary: dict = {}
            categories: list[dict] = []
            merchants: list[dict] = []
            budgets: list[dict] = []
            bills: list[dict] = []
            try:
                summary = normalize_summary(await self._get(client, "/summary/basic", start=month_start.isoformat(), end=month_end.isoformat()))
            except Exception as exc:
                errors.append(f"summary: {describe_error(exc, 'Firefly')}")
            try:
                categories = normalize_insight(await self._get(client, "/insight/expense/category", start=month_start.isoformat(), end=month_end.isoformat()))
            except Exception as exc:
                errors.append(f"categories: {describe_error(exc, 'Firefly')}")
            try:
                merchants = normalize_insight(await self._get(client, "/insight/expense/expense", start=month_start.isoformat(), end=month_end.isoformat()))
            except Exception as exc:
                errors.append(f"merchants: {describe_error(exc, 'Firefly')}")
            try:
                raw_budgets = await self._paged(client, "/budgets")

                async def limits_for(bid: str) -> list[dict]:
                    try:
                        payload = await self._get(client, f"/budgets/{bid}/limits", start=month_start.isoformat(), end=month_end.isoformat())
                        return payload.get("data") or []
                    except Exception:
                        return []

                ids = [str(b.get("id")) for b in raw_budgets]
                limits = dict(zip(ids, await asyncio.gather(*(limits_for(bid) for bid in ids)), strict=True))
                budgets = normalize_budgets(raw_budgets, limits)
            except Exception as exc:
                errors.append(f"budgets: {describe_error(exc, 'Firefly')}")
            try:
                bills = normalize_bills(await self._paged(client, "/bills", start=today.isoformat(), end=(today + timedelta(days=14)).isoformat()))
            except Exception as exc:
                errors.append(f"bills: {describe_error(exc, 'Firefly')}")

        data = {
            "about": {"version": version},
            "accounts": accounts,
            "summary": summary,
            "transactions": transactions,
            "window": {"start": start.isoformat(), "end": today.isoformat()},
            "categories": categories,
            "merchants": merchants,
            "budgets": budgets,
            "bills": bills,
            "fetched_date": today.isoformat(),
        }
        if errors:
            raise Degraded(data, "; ".join(errors))
        return data

    # ------------------------------------------------------------------
    def mock(self) -> dict:
        today = today_local()
        delta = today - FIXTURE_ANCHOR
        fx = load_fixture("firefly/firefly.json")

        def _shift(value: str | None) -> str | None:
            return shift_date(value, delta)

        groups = fx["transactions"]["data"]
        for g in groups:
            for split in g["attributes"]["transactions"]:
                split["date"] = _shift(split["date"])
        accounts = normalize_accounts(fx["accounts"]["data"])
        for a in accounts:
            a["balance_date"] = _shift(a["balance_date"])
        bills = normalize_bills(fx["bills"]["data"])
        for b in bills:
            b["next_expected"] = _shift(b["next_expected"])
        return {
            "about": {"version": fx["about"]["data"]["version"]},
            "accounts": accounts,
            "summary": normalize_summary(fx["summary"]),
            "transactions": flatten_transactions(groups),
            "window": {"start": window_start(today).isoformat(), "end": today.isoformat()},
            "categories": normalize_insight(fx["insight_category"]),
            "merchants": normalize_insight(fx["insight_expense"]),
            "budgets": normalize_budgets(fx["budgets"]["data"], {str(b["id"]): fx["budget_limits"].get(str(b["id"]), []) for b in fx["budgets"]["data"]}),
            "bills": bills,
            "fetched_date": today.isoformat(),
        }


# --------------------------------------------------------------------------
# Optional: Firefly Data Importer auto import trigger
# --------------------------------------------------------------------------
async def trigger_importer(settings) -> dict:
    """Ask the Firefly Data Importer to run its configured auto import."""
    url = settings.firefly_importer_url.rstrip("/") + "/autoimport"
    params = {"directory": settings.firefly_importer_dir, "secret": settings.firefly_importer_secret}
    async with make_client(timeout=30.0) as client:
        resp = await client.post(url, params=params, headers={"Accept": "application/json"})
    return {"status_code": resp.status_code, "ok": resp.status_code < 400, "triggered_at": iso(utcnow())}


# --------------------------------------------------------------------------
# Optional: tag write back
# --------------------------------------------------------------------------
async def add_tags_to_group(settings, group_id: str, journal_id: int, new_tags: list[str]) -> bool:
    """PUT the full split array back with extra tags on the given journal. Never drops splits or tags."""
    base = settings.firefly_url.rstrip("/") + "/api/v1"
    async with make_client(timeout=20.0, headers=bearer_headers(settings.firefly_token, FIREFLY_ACCEPT)) as client:
        resp = await request(client, "GET", f"{base}/transactions/{group_id}", service="Firefly")
        resp.raise_for_status()
        group = resp.json().get("data", {})
        attrs = group.get("attributes", {}) or {}
        splits = []
        changed = False
        for split in attrs.get("transactions", []) or []:
            tags = list(split.get("tags") or [])
            if int(split.get("transaction_journal_id") or 0) == journal_id:
                for t in new_tags:
                    if t not in tags:
                        tags.append(t)
                        changed = True
            payload = {
                "transaction_journal_id": split.get("transaction_journal_id"),
                "type": split.get("type"),
                "date": split.get("date"),
                "amount": split.get("amount"),
                "description": split.get("description"),
                "source_id": split.get("source_id"),
                "destination_id": split.get("destination_id"),
                "category_name": split.get("category_name"),
                "budget_id": split.get("budget_id"),
                "notes": split.get("notes"),
                "tags": tags,
            }
            splits.append({k: v for k, v in payload.items() if v is not None})
        if not changed:
            return False
        body = {"apply_rules": False, "fire_webhooks": False, "group_title": attrs.get("group_title"), "transactions": splits}
        resp = await request(client, "PUT", f"{base}/transactions/{group_id}", json=body, service="Firefly")
        resp.raise_for_status()
        return True
