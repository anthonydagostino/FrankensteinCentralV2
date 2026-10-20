"""Derived finance metrics from the normalized Firefly data."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from ..config_loader import DashboardConfig
from ..util import money, money_str

ZERO = Decimal("0.00")


def _d(value) -> Decimal:
    return money(value)


def firefly_links(vanity: str) -> dict:
    base = vanity.rstrip("/") if vanity else ""
    if not base:
        return {}
    return {
        "home": base,
        "accounts": f"{base}/accounts/asset",
        "budgets": f"{base}/budgets",
        "bills": f"{base}/subscriptions",
        "categories": f"{base}/categories",
        "transactions": f"{base}/transactions/withdrawal",
        "account_template": f"{base}/accounts/show/{{id}}",
        "transaction_template": f"{base}/transactions/show/{{group_id}}",
    }


def is_card_account(acct: dict) -> bool:
    if acct.get("role") == "ccAsset":
        return True
    if acct.get("type") in ("liabilities", "liability") and (acct.get("liability_type") or "").lower() in ("debt", "credit card", "creditcard"):
        return True
    return False


def owed_amount(acct: dict) -> Decimal:
    bal = _d(acct.get("balance"))
    if acct.get("type") == "asset":
        return max(ZERO, -bal)
    return abs(bal)


def group_accounts(accounts: list[dict], links: dict) -> dict:
    assets, cards, liabilities = [], [], []
    tmpl = links.get("account_template")
    for a in accounts:
        row = {
            "id": a["id"],
            "name": a["name"],
            "type": a["type"],
            "role": a.get("role"),
            "balance": a["balance"],
            "balance_date": a.get("balance_date"),
            "url": tmpl.format(id=a["id"]) if tmpl else None,
        }
        if is_card_account(a):
            row["owed"] = money_str(owed_amount(a))
            cards.append(row)
        elif a["type"] == "asset":
            assets.append(row)
        else:
            row["owed"] = money_str(abs(_d(a["balance"])))
            liabilities.append(row)
    return {"assets": assets, "credit_cards": cards, "liabilities": liabilities}


def net_worth_fallback(accounts: list[dict]) -> Decimal:
    total = ZERO
    for a in accounts:
        if a.get("include_net_worth") is False:
            continue
        bal = _d(a.get("balance"))
        if a["type"] == "asset":
            total += bal
        else:
            total -= abs(bal)
    return total


def spend_between(transactions: list[dict], start: date, end: date) -> Decimal:
    """Withdrawals only. Transfers (card payments) never count."""
    total = ZERO
    for t in transactions:
        if t.get("type") != "withdrawal":
            continue
        d = date.fromisoformat(t["date"][:10])
        if start <= d <= end:
            total += _d(t["amount"])
    return total


def daily_spend(transactions: list[dict], today: date, days: int = 30) -> list[dict]:
    start = today - timedelta(days=days - 1)
    buckets: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for t in transactions:
        if t.get("type") != "withdrawal":
            continue
        d = date.fromisoformat(t["date"][:10])
        if start <= d <= today:
            buckets[d] += _d(t["amount"])
    return [{"date": (start + timedelta(days=i)).isoformat(), "amount": money_str(buckets.get(start + timedelta(days=i), ZERO))} for i in range(days)]


def top_categories(data: dict, transactions: list[dict], month_start: date, today: date, limit: int = 6) -> list[dict]:
    cats = data.get("categories") or []
    if not cats:
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for t in transactions:
            if t.get("type") != "withdrawal":
                continue
            d = date.fromisoformat(t["date"][:10])
            if month_start <= d <= today:
                totals[t.get("category_name") or "(no category)"] += _d(t["amount"])
        cats = [{"name": k, "amount": money_str(v)} for k, v in totals.items()]
    cats = sorted(cats, key=lambda c: _d(c["amount"]), reverse=True)
    total = sum((_d(c["amount"]) for c in cats), ZERO)
    out = []
    for c in cats[:limit]:
        amt = _d(c["amount"])
        out.append({"name": c["name"], "amount": money_str(amt), "share": float(round(amt / total, 4)) if total > 0 else 0.0})
    return out


def budgets_view(data: dict) -> list[dict]:
    out = []
    for b in data.get("budgets") or []:
        limit = _d(b.get("limit"))
        spent = _d(b.get("spent"))
        pct = float(round(spent / limit * 100, 1)) if limit > 0 else None
        level = "ok"
        if pct is not None:
            if pct >= 100:
                level = "over"
            elif pct >= 85:
                level = "warn"
        out.append({"id": b["id"], "name": b["name"], "limit": money_str(limit), "spent": money_str(spent), "pct": pct, "level": level})
    out.sort(key=lambda b: -(b["pct"] or 0))
    return out


def upcoming_bills(data: dict, today: date, days: int = 14) -> list[dict]:
    out = []
    for b in data.get("bills") or []:
        nxt = b.get("next_expected")
        if not nxt:
            continue
        d = date.fromisoformat(nxt[:10])
        if today <= d <= today + timedelta(days=days):
            out.append({"id": b["id"], "name": b["name"], "amount": b.get("amount_max") or b.get("amount_min"), "due": d.isoformat(), "days": (d - today).days, "paid": b.get("paid_this_period", False)})
    out.sort(key=lambda b: b["due"])
    return out


def recent_transactions(transactions: list[dict], links: dict, limit: int = 15) -> list[dict]:
    tmpl = links.get("transaction_template")
    rows = sorted(transactions, key=lambda t: (t["date"], t["journal_id"]), reverse=True)[:limit]
    out = []
    for t in rows:
        if t["type"] == "withdrawal":
            account = t.get("source_name")
            counterparty = t.get("destination_name")
            sign = -1
        elif t["type"] == "deposit":
            account = t.get("destination_name")
            counterparty = t.get("source_name")
            sign = 1
        else:
            account = f"{t.get('source_name')} to {t.get('destination_name')}"
            counterparty = None
            sign = 0
        out.append(
            {
                "journal_id": t["journal_id"],
                "group_id": t["group_id"],
                "date": t["date"],
                "description": t["description"],
                "amount": t["amount"],
                "sign": sign,
                "type": t["type"],
                "account": account,
                "counterparty": counterparty,
                "category": t.get("category_name") or None,
                "url": tmpl.format(group_id=t["group_id"]) if tmpl else None,
            }
        )
    return out


def freshness(data: dict, accounts: list[dict], now: datetime, stale_after_hours: int) -> dict:
    """Newest transaction per bank fed account (external_id present, or any card account)."""
    newest: dict[str, str] = {}
    name_by_id = {a["id"]: a["name"] for a in accounts}
    card_ids = {a["id"] for a in accounts if is_card_account(a)}
    for t in data.get("transactions") or []:
        for key in ("source_id", "destination_id"):
            aid = t.get(key)
            if aid in name_by_id and (t.get("external_id") or aid in card_ids):
                if t["date"] > newest.get(aid, ""):
                    newest[aid] = t["date"]
    per_account = [{"account_id": aid, "account": name_by_id[aid], "newest": d} for aid, d in newest.items()]
    per_account.sort(key=lambda r: r["newest"], reverse=True)
    overall = max(newest.values()) if newest else None
    hours = None
    stale = False
    if overall:
        newest_dt = datetime.fromisoformat(overall[:10]).replace(tzinfo=now.tzinfo)
        hours = round((now - newest_dt).total_seconds() / 3600, 1)
        stale = hours > stale_after_hours
    return {"newest_transaction": overall, "hours_since": hours, "stale": stale, "stale_after_hours": stale_after_hours, "per_account": per_account[:8]}


def build_summary(data: dict, config: DashboardConfig, vanity_url: str, today: date, now: datetime) -> dict:
    links = firefly_links(vanity_url)
    accounts = data.get("accounts") or []
    transactions = data.get("transactions") or []
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    same_day_last_month = min(last_month_start + timedelta(days=today.day - 1), last_month_end)

    summary = data.get("summary") or {}
    net_worth = _d(summary.get("net_worth")) if summary.get("net_worth") is not None else net_worth_fallback(accounts)
    mtd = spend_between(transactions, month_start, today)
    last = spend_between(transactions, last_month_start, same_day_last_month)
    if last > 0:
        pace_pct = float(round((mtd - last) / last * 100, 1))
        pace = "ahead" if mtd > last else "behind"
    else:
        pace_pct = None
        pace = None
    left = summary.get("left_to_spend")
    return {
        "currency": config.finance.currency,
        "firefly_version": (data.get("about") or {}).get("version"),
        "net_worth": money_str(net_worth),
        "mtd_spend": money_str(mtd),
        "last_month_same_day": money_str(last),
        "pace": pace,
        "pace_pct": pace_pct,
        "left_to_spend": left,
        "earned_mtd": summary.get("earned"),
        "bills_unpaid": summary.get("bills_unpaid"),
        "daily_spend": daily_spend(transactions, today),
        "categories": top_categories(data, transactions, month_start, today),
        "budgets": budgets_view(data),
        "bills": upcoming_bills(data, today),
        "accounts": group_accounts(accounts, links),
        "freshness": freshness(data, accounts, now, config.finance.stale_after_hours),
        "links": links,
        "privacy_default": config.finance.hide_amounts_by_default,
    }
