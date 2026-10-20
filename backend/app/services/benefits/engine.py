"""Per benefit, per period results and the /api/benefits response."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ...config_loader import BenefitsCatalog, CardConfig
from ...util import money
from .catalog import Benefit, benefits_for_card, load_catalog
from .classify import Classified, classify_card
from .match import attribute
from .periods import Period, cap_for, current_period, next_eligible, period_for, periods_in_year

ZERO = Decimal("0.00")
MISSING_CREDIT_DAYS = 14
MISSING_CREDIT_ATTENTION_DAYS = 60
PENDING_WINDOW_DAYS = 60
EXPIRING_SOON_DAYS = 14
EXPIRING_MIN_REMAINING = Decimal("1.00")


def _s(d: Decimal) -> str:
    return f"{money(d):.2f}"


def period_result(benefit: Benefit, period: Period, items: list[Classified], manual: dict[str, Decimal], today: date) -> dict:
    cap = cap_for(benefit, period)
    in_period = [c for c in items if c.benefit_id == benefit.id and c.period_key == period.key]
    credits = [c for c in in_period if c.kind == "statement_credit"]
    clawbacks = [c for c in in_period if c.kind == "credit_clawback"]
    purchases = [c for c in in_period if c.kind == "purchase" and c.eligible]

    credit_total = ZERO
    for c in sorted(credits, key=lambda x: (x.date, x.journal_id)):
        if c.extra.get("clawed_back"):
            c.note = (c.note + "; " if c.note else "") + "reversed by a later clawback"
        if credit_total >= cap:
            c.over_cap = True
            c.note = (c.note + "; " if c.note else "") + "over cap"
        elif credit_total + c.amount > cap:
            c.over_cap = True
            c.note = (c.note + "; " if c.note else "") + f"over cap by {_s(credit_total + c.amount - cap)}"
        credit_total += c.amount
    clawback_total = sum((c.amount for c in clawbacks), ZERO)
    credits_net = credit_total - clawback_total

    used = ZERO
    manual_used = manual.get(period.key)
    if benefit.tracking == "manual":
        if manual_used is not None:
            used = min(cap, max(ZERO, manual_used))
    else:
        used = min(cap, max(ZERO, credits_net))

    net_eligible_spend = sum((p.amount - p.refunded for p in purchases), ZERO)
    pending = ZERO
    if benefit.tracking == "matched":
        recent_unmatched = sum((p.remaining_unmatched for p in purchases if (today - p.date).days <= PENDING_WINDOW_DAYS), ZERO)
        pending = min(max(ZERO, cap - used), max(ZERO, recent_unmatched))
    remaining = max(ZERO, cap - used - pending)

    missing_credit = None
    missing_age = 0
    if benefit.tracking == "matched" and used < cap:
        for p in sorted(purchases, key=lambda x: x.date):
            age = (today - p.date).days
            if age > MISSING_CREDIT_DAYS and p.credited == ZERO and p.remaining_unmatched > ZERO:
                missing_credit = f"No credit yet for ${_s(p.amount)} at {p.description.strip()} on {p.date.strftime('%b %-d')}. Check that the benefit is enrolled."
                missing_age = age
                break

    ended = period.ended(today)
    if benefit.tracking == "manual":
        if manual_used is None:
            status = "expired_unused" if ended else "manual"
        elif used >= cap:
            status = "used"
        elif ended:
            status = "expired_partial" if used > ZERO else "expired_unused"
        else:
            status = "partial" if used > ZERO else "manual"
    elif ended:
        if used <= ZERO:
            status = "expired_unused"
        elif used < cap:
            status = "expired_partial"
        else:
            status = "used"
    else:
        if used >= cap:
            status = "used"
        elif pending > ZERO and used + pending >= cap:
            status = "pending"
        elif used > ZERO or pending > ZERO:
            status = "partial"
        else:
            status = "unused"

    days_left = period.days_left(today)
    return {
        "period_key": period.key,
        "label": period.label,
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "days_left": days_left,
        "ended": ended,
        "cap": _s(cap),
        "used": _s(used),
        "pending": _s(pending),
        "remaining": _s(remaining),
        "credits_gross": _s(credit_total),
        "clawbacks": _s(clawback_total),
        "net_eligible_spend": _s(net_eligible_spend),
        "status": status,
        "expiring_soon": (not ended) and remaining >= EXPIRING_MIN_REMAINING and days_left <= EXPIRING_SOON_DAYS,
        "missing_credit": missing_credit,
        "missing_credit_age_days": missing_age if missing_credit else None,
        "manual_entry": _s(manual_used) if manual_used is not None else None,
    }


def multi_year_result(benefit: Benefit, items: list[Classified], today: date) -> dict:
    credits = sorted([c for c in items if c.benefit_id == benefit.id and c.kind == "statement_credit"], key=lambda c: c.date)
    purchases = sorted([c for c in items if c.benefit_id == benefit.id and c.kind == "purchase" and c.eligible], key=lambda c: c.date)
    last_credit = credits[-1] if credits else None
    last_used = last_credit.date if last_credit else None
    nxt = next_eligible(last_used, benefit.period_years)
    eligible_now = nxt is None or nxt <= today
    pending = ZERO
    if purchases and (not last_credit or purchases[-1].date > last_credit.date) and (today - purchases[-1].date).days <= PENDING_WINDOW_DAYS:
        pending = min(benefit.cap, purchases[-1].amount)
    return {
        "period_key": "multi_year",
        "label": f"Every {benefit.period_years:g} years",
        "start": None,
        "end": nxt.isoformat() if nxt else None,
        "days_left": (nxt - today).days if nxt and nxt > today else 0,
        "ended": False,
        "cap": _s(benefit.cap),
        "used": _s(min(benefit.cap, last_credit.amount)) if last_credit and not eligible_now else "0.00",
        "pending": _s(pending),
        "remaining": _s(benefit.cap) if eligible_now and pending == ZERO else "0.00",
        "status": "unused" if eligible_now and pending == ZERO else ("pending" if pending > ZERO else "used"),
        "expiring_soon": False,
        "missing_credit": None,
        "missing_credit_age_days": None,
        "last_used": last_used.isoformat() if last_used else None,
        "next_eligible": nxt.isoformat() if nxt else None,
        "manual_entry": None,
    }


class BenefitsEngine:
    def __init__(self, catalog: BenefitsCatalog, cards: list[CardConfig]):
        self.catalog = catalog
        self.benefits = load_catalog(catalog)
        self.cards = cards

    def compute(
        self,
        transactions: list[dict],
        card_accounts: dict[str, dict | None],
        overrides: dict[int, dict],
        manual_usage: dict[str, dict[str, Decimal]],
        today: date,
        year: int,
    ) -> dict:
        """card_accounts: card id -> {"id": account id, "name": account name} or None."""
        cards_out = []
        expiring: list[dict] = []
        attention: list[dict] = []
        all_classified: dict[str, list[Classified]] = {}
        for card in self.cards:
            acct = card_accounts.get(card.id)
            benefits = benefits_for_card(self.benefits, card.id)
            items: list[Classified] = []
            if acct:
                account_id = str(acct["id"])
                rows = [t for t in transactions if str(t.get("source_id")) == account_id or str(t.get("destination_id")) == account_id]
                items = classify_card(rows, account_id, acct.get("name", card.label), benefits, overrides)
                for b in benefits:
                    attribute(b, items)
            all_classified[card.id] = items

            captured = ZERO
            left_on_table = ZERO
            still_available = ZERO
            benefits_out = []
            for b in benefits:
                manual = manual_usage.get(b.id, {})
                evidence = sorted([c for c in items if c.benefit_id == b.id], key=lambda c: (c.date, c.journal_id))
                if b.period == "multi_year":
                    current = multi_year_result(b, items, today)
                    history: list[dict] = []
                    captured += Decimal(current["used"])
                    benefits_out.append(self._benefit_out(b, current, history, evidence))
                    continue
                periods = periods_in_year(b.period, year, b.active_from, b.active_until)
                # include last year's periods that still have evidence (early January view)
                extra_keys = {c.period_key for c in evidence if c.period_key and not c.period_key.startswith(str(year))}
                for key in sorted(extra_keys):
                    try:
                        sample = next(c for c in evidence if c.period_key == key)
                        p = period_for(b.period, sample.date if sample.kind == "purchase" else sample.date - timedelta(days=3))
                        if p.key == key and p not in periods:
                            periods.append(p)
                    except StopIteration:
                        pass
                periods = [p for p in periods if p.start <= today]
                periods.sort(key=lambda p: p.start)
                results = [period_result(b, p, items, manual, today) for p in periods]
                cur_period = current_period(b, today)
                current = next((r for r in results if cur_period and r["period_key"] == cur_period.key), None)
                history = [r for r in results if not current or r["period_key"] != current["period_key"]]
                for r in results:
                    if r["period_key"].startswith(str(year)):
                        captured += Decimal(r["used"])
                        if r["ended"]:
                            left_on_table += max(ZERO, Decimal(r["cap"]) - Decimal(r["used"]))
                if current:
                    still_available += Decimal(current["remaining"])
                    if current["expiring_soon"]:
                        expiring.append({"card": card.id, "card_label": card.label, "id": b.id, "name": b.name, "remaining": current["remaining"], "days_left": current["days_left"]})
                    if current.get("missing_credit") and (current.get("missing_credit_age_days") or 0) >= MISSING_CREDIT_ATTENTION_DAYS:
                        attention.append({"card": card.id, "card_label": card.label, "id": b.id, "name": b.name, "message": current["missing_credit"]})
                for r in history:
                    if r.get("missing_credit") and (r.get("missing_credit_age_days") or 0) >= MISSING_CREDIT_ATTENTION_DAYS and not r["ended"]:
                        attention.append({"card": card.id, "card_label": card.label, "id": b.id, "name": b.name, "message": r["missing_credit"]})
                benefits_out.append(self._benefit_out(b, current, history, evidence))

            fee = Decimal(card.annual_fee)
            cards_out.append(
                {
                    "card": card.id,
                    "label": card.label,
                    "annual_fee": _s(fee),
                    "account": acct,
                    "captured_ytd": _s(captured),
                    "fee_offset": float(round(captured / fee, 4)) if fee > 0 else None,
                    "left_on_table_ytd": _s(left_on_table),
                    "still_available": _s(still_available),
                    "benefits": benefits_out,
                }
            )
        return {
            "year": year,
            "today": today.isoformat(),
            "catalog_last_verified": self.catalog.last_verified.isoformat(),
            "cards": cards_out,
            "expiring_soon": sorted(expiring, key=lambda e: e["days_left"]),
            "missing_credits": attention,
            "_classified": all_classified,
        }

    @staticmethod
    def _benefit_out(b: Benefit, current: dict | None, history: list[dict], evidence: list[Classified]) -> dict:
        return {
            "id": b.id,
            "name": b.name,
            "tracking": b.tracking,
            "period": b.period,
            "cap": _s(b.cap),
            "enrollment_required": b.enrollment_required,
            "active_from": b.active_from.isoformat() if b.active_from else None,
            "active_until": b.active_until.isoformat() if b.active_until else None,
            "notes": b.notes,
            "current": current,
            "history": history,
            "evidence": [c.as_evidence() for c in evidence],
        }

    @staticmethod
    def unclassified(result: dict, today: date, days: int = 120) -> list[dict]:
        """Unclassified deposits and low confidence items from the last N days."""
        cutoff = today - timedelta(days=days)
        out = []
        for card_id, items in result.get("_classified", {}).items():
            for c in items:
                if c.date < cutoff:
                    continue
                if c.kind == "unclassified_deposit" or (c.confidence == "low" and not c.override):
                    out.append(
                        {
                            "card": card_id,
                            "journal_id": c.journal_id,
                            "group_id": c.group_id,
                            "date": c.date.isoformat(),
                            "amount": _s(c.amount),
                            "description": c.description,
                            "account": c.account_name,
                            "kind": c.kind,
                            "benefit_id": c.benefit_id,
                            "confidence": c.confidence,
                            "note": c.note,
                        }
                    )
        out.sort(key=lambda r: r["date"], reverse=True)
        return out


def strip_internal(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}
