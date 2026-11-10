"""Amex card account resolution and card metrics."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ..config_loader import CardConfig
from ..db import Database
from ..util import compile_pattern, money, money_str
from .benefits.classify import Classified
from .finance import owed_amount

ZERO = Decimal("0.00")


def resolve_card_accounts(cards: list[CardConfig], accounts: list[dict[str, Any]], db: Database | None) -> dict[str, dict[str, Any] | None]:
    """Map each configured card to a Firefly account: a pinned setting wins, then the configured id, then the name regex."""
    out: dict[str, dict[str, Any] | None] = {}
    by_id = {a["id"]: a for a in accounts}
    for card in cards:
        chosen = None
        pinned = db.get_setting(f"card_account:{card.id}") if db else None
        if pinned and pinned in by_id:
            chosen = by_id[pinned]
        elif card.firefly_account_id is not None and str(card.firefly_account_id) in by_id:
            chosen = by_id[str(card.firefly_account_id)]
        elif card.firefly_account_match:
            rx = compile_pattern(card.firefly_account_match)
            for a in accounts:
                if rx.search(a["name"]):
                    chosen = a
                    break
        out[card.id] = (
            {"id": chosen["id"], "name": chosen["name"], "type": chosen["type"], "role": chosen.get("role"), "pinned": bool(pinned)} if chosen else None
        )
    return out


def card_metrics(
    card: CardConfig,
    account: dict[str, Any] | None,
    accounts: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    classified: list[Classified],
    benefits_card: dict[str, Any] | None,
    today: date,
    links: dict[str, Any],
) -> dict[str, Any]:
    """Balance, spend, largest purchase, last credit, and fee offset for one card."""
    base: dict[str, Any] = {"id": card.id, "label": card.label, "annual_fee": money_str(card.annual_fee), "account": account}
    if account is None:
        base.update({"configured": False, "message": "No Firefly account matched. Pin one on the Settings page."})
        return base
    acct = next((a for a in accounts if a["id"] == account["id"]), None)
    aid = account["id"]
    month_start = today.replace(day=1)
    last30 = today - timedelta(days=29)
    purchases = [t for t in transactions if t.get("type") == "withdrawal" and str(t.get("source_id")) == aid]
    this_month = [t for t in purchases if month_start <= date.fromisoformat(t["date"][:10]) <= today]
    recent = [t for t in purchases if last30 <= date.fromisoformat(t["date"][:10]) <= today]
    largest = max(this_month, key=lambda t: money(t["amount"]), default=None)
    credits = sorted([c for c in classified if c.kind == "statement_credit"], key=lambda c: (c.date, c.journal_id))
    last_credit = credits[-1] if credits else None
    captured = Decimal(benefits_card["captured_ytd"]) if benefits_card else ZERO
    fee = Decimal(card.annual_fee)
    return {
        **base,
        "configured": True,
        "balance": money_str(owed_amount(acct)) if acct else None,
        "balance_date": acct.get("balance_date") if acct else None,
        "credit_limit": acct.get("credit_limit") if acct else None,
        "spend_month": money_str(sum((money(t["amount"]) for t in this_month), ZERO)),
        "spend_30d": money_str(sum((money(t["amount"]) for t in recent), ZERO)),
        "largest_purchase": {"description": largest["description"], "amount": largest["amount"], "date": largest["date"]} if largest else None,
        "last_credit": {
            "description": last_credit.description,
            "amount": money_str(last_credit.amount),
            "date": last_credit.date.isoformat(),
            "benefit_id": last_credit.benefit_id,
        }
        if last_credit
        else None,
        "captured_ytd": money_str(captured),
        "fee_offset": float(round(captured / fee, 4)) if fee > 0 else None,
        "still_available": benefits_card["still_available"] if benefits_card else None,
        "url": links.get("account_template", "").format(id=aid) if links.get("account_template") else None,
    }
