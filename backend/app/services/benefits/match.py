"""Attribute statement credits, refunds, and clawbacks to purchases and periods."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .catalog import Benefit
from .classify import Classified
from .periods import cap_for, period_for

CREDIT_LOOKBACK_DAYS = 60
REFUND_LOOKBACK_DAYS = 120
CREDIT_DATE_SHIFT_DAYS = 3
TOLERANCE = Decimal("0.01")


def attribute(benefit: Benefit, items: list[Classified]) -> None:
    """Mutates the Classified rows for one benefit: sets period_key, matched_purchase, attribution."""
    kind = benefit.period
    purchases = sorted([c for c in items if c.kind == "purchase" and c.benefit_id == benefit.id], key=lambda c: (c.date, c.journal_id))
    credits = sorted([c for c in items if c.kind == "statement_credit" and c.benefit_id == benefit.id], key=lambda c: (c.date, c.journal_id))
    refunds = sorted([c for c in items if c.kind == "merchant_refund" and c.benefit_id == benefit.id], key=lambda c: (c.date, c.journal_id))
    clawbacks = sorted([c for c in items if c.kind == "credit_clawback" and c.benefit_id == benefit.id], key=lambda c: (c.date, c.journal_id))

    for p in purchases:
        p.period_key = p.override_period_key or period_for(kind, p.date).key
        p.remaining_unmatched = p.amount
        p.refunded = Decimal("0")
        p.credited = Decimal("0")

    eligible = [p for p in purchases if p.eligible]
    credited_by_period: dict[str, Decimal] = {}

    def period_cap(key: str, sample_date: date) -> Decimal:
        return cap_for(benefit, period_for(kind, sample_date))

    def close_period_if_full(key: str, sample_date: date) -> None:
        # once the cap is hit, leftover purchase amounts in that period can never earn more credit
        if credited_by_period.get(key, Decimal("0")) + TOLERANCE >= period_cap(key, sample_date):
            for p in eligible:
                if p.period_key == key:
                    p.remaining_unmatched = Decimal("0")

    # credits: earliest purchase on or before the credit date, within 60 days, with enough unmatched amount,
    # in a period that still has cap available
    for cr in credits:
        cr.matched_purchase = None
        if benefit.tracking == "matched":
            for p in eligible:
                if p.date > cr.date:
                    break
                if (cr.date - p.date).days > CREDIT_LOOKBACK_DAYS:
                    continue
                if credited_by_period.get(p.period_key or "", Decimal("0")) + TOLERANCE >= period_cap(p.period_key or "", p.date):
                    continue
                if p.remaining_unmatched + TOLERANCE >= cr.amount:
                    p.remaining_unmatched = max(Decimal("0"), p.remaining_unmatched - cr.amount)
                    p.credited += cr.amount
                    cr.matched_purchase = p.journal_id
                    cr.period_key = p.period_key
                    cr.attribution = "by_purchase"
                    break
        if cr.override_period_key:
            cr.period_key = cr.override_period_key
            cr.attribution = "override"
        elif cr.matched_purchase is None:
            shifted = cr.date - timedelta(days=CREDIT_DATE_SHIFT_DAYS)
            cr.period_key = period_for(kind, shifted).key
            cr.attribution = "by_credit_date"
            # consume unmatched spend in that period so pending and missing credit stay honest
            left = cr.amount
            for p in eligible:
                if left <= 0:
                    break
                if p.period_key == cr.period_key and p.date <= cr.date and p.remaining_unmatched > 0:
                    take = min(left, p.remaining_unmatched)
                    p.remaining_unmatched -= take
                    p.credited += take
                    left -= take
        if cr.period_key:
            credited_by_period[cr.period_key] = credited_by_period.get(cr.period_key, Decimal("0")) + cr.amount
            sample = next((p.date for p in eligible if p.period_key == cr.period_key), cr.date - timedelta(days=CREDIT_DATE_SHIFT_DAYS))
            close_period_if_full(cr.period_key, sample)

    # refunds: earliest purchase with an equal or larger amount within 120 days before the refund
    for rf in refunds:
        rf.matched_purchase = None
        for p in purchases:
            if p.date > rf.date:
                break
            if (rf.date - p.date).days > REFUND_LOOKBACK_DAYS:
                continue
            if p.amount - p.refunded + TOLERANCE >= rf.amount:
                p.refunded += rf.amount
                p.remaining_unmatched = max(Decimal("0"), p.remaining_unmatched - rf.amount)
                rf.matched_purchase = p.journal_id
                rf.period_key = p.period_key
                rf.attribution = "by_purchase"
                break
        if rf.period_key is None:
            rf.period_key = rf.override_period_key or period_for(kind, rf.date).key
            rf.attribution = "by_refund_date"

    # clawbacks: most recent prior credit with the same amount, else the most recent prior credit
    for cb in clawbacks:
        prior = [c for c in credits if c.date <= cb.date]
        same = [c for c in prior if c.amount == cb.amount and not c.extra.get("clawed_back")]
        target = (same or [c for c in prior if not c.extra.get("clawed_back")] or [None])[-1]
        if target is not None:
            target.extra["clawed_back"] = True
            cb.matched_purchase = target.matched_purchase
            cb.period_key = target.period_key
            cb.attribution = "by_credit"
            cb.extra["reverses"] = target.journal_id
        else:
            cb.period_key = cb.override_period_key or period_for(kind, cb.date).key
            cb.attribution = "by_clawback_date"
