"""Transaction classification for Amex benefits."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ...util import money
from .catalog import Benefit

GENERIC_CREDIT_MARKERS = re.compile(r"\b(credit|stmt cr|statement credit|amex|american express|platinum)\b", re.I)
PAYMENT_MARKERS = re.compile(r"(payment|thank you|autopay|epayment|online pmt|ach pmt|mobile pmt)", re.I)
REVERSAL_MARKERS = re.compile(r"(reversal|adjustment|rev\b|clawback)", re.I)
CLAWBACK_MARKERS = re.compile(r"(credit|reversal|adjustment|rev\b|clawback)", re.I)

CREDIT_LOOKBACK_DAYS = 60
MEDIUM_CONFIDENCE_WINDOW_DAYS = 21


@dataclass
class Classified:
    journal_id: int
    group_id: str
    date: date
    amount: Decimal
    description: str
    account_name: str
    kind: str  # purchase | merchant_refund | statement_credit | credit_clawback | payment | other | unclassified_deposit
    benefit_id: str | None = None
    confidence: str | None = None  # high | medium | low
    eligible: bool = False
    override: bool = False
    override_period_key: str | None = None
    note: str | None = None
    # filled by match.py
    period_key: str | None = None
    attribution: str | None = None
    matched_purchase: int | None = None
    over_cap: bool = False
    # purchase bookkeeping
    remaining_unmatched: Decimal = Decimal("0")
    refunded: Decimal = Decimal("0")
    credited: Decimal = Decimal("0")
    extra: dict[str, Any] = field(default_factory=dict)

    def as_evidence(self) -> dict:
        out = {
            "journal_id": self.journal_id,
            "date": self.date.isoformat(),
            "kind": self.kind,
            "amount": f"{self.amount:.2f}",
            "description": self.description,
            "period_key": self.period_key,
            "confidence": self.confidence,
            "matched_purchase": self.matched_purchase,
            "attribution": self.attribution,
            "override": self.override,
            "over_cap": self.over_cap,
            "note": self.note,
        }
        if self.kind == "purchase":
            out["refunded"] = f"{self.refunded:.2f}"
            out["credited"] = f"{self.credited:.2f}"
        return out


def text_of(row: dict, account_id: str | None = None) -> str:
    """Description, notes, and the counterparty name. The card's own account name is left out."""
    parts = [str(row.get("description") or ""), str(row.get("notes") or "")]
    if account_id is None or str(row.get("source_id")) != str(account_id):
        parts.append(str(row.get("source_name") or ""))
    if account_id is None or str(row.get("destination_id")) != str(account_id):
        parts.append(str(row.get("destination_name") or ""))
    return " ".join(parts).lower()


def own_text(row: dict) -> str:
    """Description and notes only, used for generic credit markers."""
    return " ".join(str(row.get(k) or "") for k in ("description", "notes")).lower()


def direction(row: dict, account_id: str) -> str:
    """inflow, outflow, payment, or none relative to the card account."""
    t = row.get("type")
    src = str(row.get("source_id")) if row.get("source_id") is not None else None
    dst = str(row.get("destination_id")) if row.get("destination_id") is not None else None
    if t == "withdrawal" and src == account_id:
        return "outflow"
    if t == "deposit" and dst == account_id:
        return "inflow"
    if t == "transfer":
        if dst == account_id:
            return "payment"
        if src == account_id:
            return "outflow_transfer"
    return "none"


def _base(row: dict, kind: str, account_name: str) -> Classified:
    return Classified(
        journal_id=int(row.get("journal_id") or 0),
        group_id=str(row.get("group_id") or ""),
        date=date.fromisoformat(str(row["date"])[:10]),
        amount=money(row.get("amount")),
        description=str(row.get("description") or ""),
        account_name=account_name,
        kind=kind,
    )


def classify_card(rows: list[dict], account_id: str, account_name: str, benefits: list[Benefit], overrides: dict[int, dict]) -> list[Classified]:
    """Classify every split that touches the card account. Purchases first, then deposits in date order."""
    rows = sorted(rows, key=lambda r: (str(r["date"])[:10], int(r.get("journal_id") or 0)))
    out: list[Classified] = []
    purchases_by_benefit: dict[str, list[Classified]] = {}

    # pass 1: outflows (purchases, clawbacks) and payments
    for row in rows:
        d = direction(row, account_id)
        if d == "none":
            continue
        journal_id = int(row.get("journal_id") or 0)
        override = overrides.get(journal_id)
        if d == "payment":
            c = _base(row, "payment", account_name)
            out.append(c)
            continue
        if d == "outflow_transfer":
            out.append(_base(row, "other", account_name))
            continue
        if d != "outflow":
            continue
        text = text_of(row, account_id)
        c = _base(row, "other", account_name)
        if override:
            cls = override.get("classification")
            if cls in ("purchase", "credit_clawback", "ignore", "other"):
                c.kind = "other" if cls == "ignore" else cls
                c.benefit_id = override.get("benefit_id") if cls != "ignore" else None
                c.override = True
                c.override_period_key = override.get("period_key")
                c.confidence = "high"
                if c.kind == "purchase" and c.benefit_id:
                    c.eligible = True
                    c.remaining_unmatched = c.amount
                    purchases_by_benefit.setdefault(c.benefit_id, []).append(c)
                out.append(c)
                continue
        matched = False
        for b in benefits:
            if b.tracking == "manual":
                continue
            # clawback: looks like a credit description on a withdrawal, or reversal/adjustment with the merchant
            if (b.matches_credit(text) and CLAWBACK_MARKERS.search(text)) or (REVERSAL_MARKERS.search(text) and b.matches_merchant(text)):
                c.kind = "credit_clawback"
                c.benefit_id = b.id
                c.confidence = "high"
                matched = True
                break
        if not matched:
            for b in benefits:
                if b.tracking != "matched" or not b.purchase_patterns:
                    continue
                if b.matches_merchant(text) and not b.matches_exclude(text):
                    c.kind = "purchase"
                    c.benefit_id = b.id
                    c.eligible = b.is_active_on(c.date)
                    c.confidence = "high"
                    c.remaining_unmatched = c.amount
                    if not c.eligible:
                        c.note = "outside the benefit's active dates"
                    purchases_by_benefit.setdefault(b.id, []).append(c)
                    matched = True
                    break
                if b.matches_merchant(text) and b.matches_exclude(text):
                    c.kind = "purchase"
                    c.benefit_id = b.id
                    c.eligible = False
                    c.confidence = "high"
                    c.note = "excluded by pattern (gift card, outlet, or similar)"
                    matched = True
                    break
        out.append(c)

    # pass 2: inflows (statement credits, refunds, unclassified deposits)
    for row in rows:
        if direction(row, account_id) != "inflow":
            continue
        journal_id = int(row.get("journal_id") or 0)
        text = text_of(row, account_id)
        desc = own_text(row)
        c = _base(row, "unclassified_deposit", account_name)
        override = overrides.get(journal_id)
        if override:
            cls = override.get("classification")
            c.override = True
            c.confidence = "high"
            c.override_period_key = override.get("period_key")
            if cls == "statement_credit":
                c.kind = "statement_credit"
                c.benefit_id = override.get("benefit_id")
            elif cls == "merchant_refund":
                c.kind = "merchant_refund"
                c.benefit_id = override.get("benefit_id") or _merchant_for(text, benefits)
            elif cls == "payment":
                c.kind = "payment"
            else:
                c.kind = "other"
            out.append(c)
            continue
        if PAYMENT_MARKERS.search(desc) and not GENERIC_CREDIT_MARKERS.search(desc):
            c.kind = "payment"
            out.append(c)
            continue
        decided = False
        # rule 2: explicit credit patterns, or generic credit markers plus the merchant
        for b in benefits:
            if b.tracking == "manual":
                continue
            if b.matches_credit(text) or (GENERIC_CREDIT_MARKERS.search(desc) and b.matches_merchant(text)):
                c.kind = "statement_credit"
                c.benefit_id = b.id
                c.confidence = "high"
                decided = True
                break
        # rule 3: merchant text only, for matched benefits
        if not decided:
            for b in benefits:
                if b.tracking != "matched" or not b.matches_merchant(text):
                    continue
                prior = [
                    p
                    for p in purchases_by_benefit.get(b.id, [])
                    if p.eligible and 0 <= (c.date - p.date).days <= CREDIT_LOOKBACK_DAYS
                ]
                cap = b.cap
                exact = [p for p in prior if p.amount == c.amount]
                if exact and c.amount > cap:
                    c.kind, c.benefit_id, c.confidence = "merchant_refund", b.id, "high"
                elif c.amount <= cap and any(p.amount >= c.amount and (c.date - p.date).days <= MEDIUM_CONFIDENCE_WINDOW_DAYS for p in prior):
                    c.kind, c.benefit_id, c.confidence = "statement_credit", b.id, "medium"
                elif exact and c.amount <= cap:
                    c.kind, c.benefit_id, c.confidence = "statement_credit", b.id, "low"
                    c.note = "ambiguous: same amount as a purchase at or under the cap"
                else:
                    c.kind, c.benefit_id, c.confidence = "merchant_refund", b.id, "medium"
                decided = True
                break
        out.append(c)

    out.sort(key=lambda c: (c.date, c.journal_id))
    return out


def _merchant_for(text: str, benefits: list[Benefit]) -> str | None:
    for b in benefits:
        if b.matches_merchant(text):
            return b.id
    return None


def suggest_pattern(description: str) -> str:
    """Escape a description into a regex and collapse digit runs to \\d+."""
    text = description.strip()
    text = re.sub(r"\s+", " ", text)
    escaped = re.escape(text)
    escaped = re.sub(r"(\\?\d)+", r"\\d+", escaped)
    escaped = escaped.replace("\\ ", " ?")
    return escaped
