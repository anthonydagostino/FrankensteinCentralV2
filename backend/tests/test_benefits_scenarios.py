"""The 18 scenarios from SPEC.md section 12.2."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from freezegun import freeze_time

from app.services.benefits.engine import BenefitsEngine

from .conftest import benefit, tx


def cur(result, bid):
    return benefit(result, bid)["current"]


def hist(result, bid, key):
    return next(h for h in benefit(result, bid)["history"] if h["period_key"] == key)


def evidence(result, bid, kind=None):
    ev = benefit(result, bid)["evidence"]
    return [e for e in ev if kind is None or e["kind"] == kind]


def test_01_core_case(run):
    rows = [tx("2026-10-03", "purchase", "120.00", "LULULEMON ATHLETICA"), tx("2026-10-06", "deposit", "75.00", "PLATINUM LULULEMON CREDIT")]
    c = cur(run(rows, date(2026, 10, 20)), "plat_lululemon")
    assert (c["period_key"], c["used"], c["pending"], c["remaining"], c["status"]) == ("2026-Q4", "75.00", "0.00", "0.00", "used")
    assert c["days_left"] == 72


def test_02_two_partial_credits(run):
    rows = [
        tx("2026-10-03", "purchase", "40.00", "LULULEMON ATHLETICA"),
        tx("2026-10-05", "deposit", "40.00", "PLATINUM LULULEMON CREDIT"),
        tx("2026-11-10", "purchase", "50.00", "LULULEMON ATHLETICA"),
        tx("2026-11-12", "deposit", "35.00", "PLATINUM LULULEMON CREDIT"),
    ]
    c = cur(run(rows, date(2026, 11, 20)), "plat_lululemon")
    assert (c["used"], c["remaining"], c["pending"]) == ("75.00", "0.00", "0.00")


def test_03_credit_crosses_year_boundary(run):
    rows = [tx("2026-12-29", "purchase", "60.00", "LULULEMON ATHLETICA"), tx("2027-01-02", "deposit", "60.00", "PLATINUM LULULEMON CREDIT")]
    last_year = run(rows, date(2027, 1, 5), year=2026)
    q4 = hist(last_year, "plat_lululemon", "2026-Q4")
    assert (q4["used"], q4["status"]) == ("60.00", "expired_partial")
    this_year = run(rows, date(2027, 1, 5), year=2027)
    q1 = cur(this_year, "plat_lululemon")
    assert (q1["period_key"], q1["used"]) == ("2027-Q1", "0.00")
    # the credit is still attributed to Q4 in the 2027 view's history
    assert hist(this_year, "plat_lululemon", "2026-Q4")["used"] == "60.00"


def test_04_pending_credit(run):
    rows = [tx("2026-10-03", "purchase", "100.00", "LULULEMON ATHLETICA")]
    c = cur(run(rows, date(2026, 10, 5)), "plat_lululemon")
    assert (c["used"], c["pending"], c["remaining"], c["status"]) == ("0.00", "75.00", "0.00", "pending")
    assert c["missing_credit"] is None


def test_05_missing_credit_after_14_days(run):
    rows = [tx("2026-10-03", "purchase", "100.00", "LULULEMON ATHLETICA")]
    c = cur(run(rows, date(2026, 10, 20)), "plat_lululemon")
    assert c["pending"] == "75.00"
    assert c["missing_credit"] and "$100.00" in c["missing_credit"] and "enrolled" in c["missing_credit"]


def test_06_refund_and_clawback(run):
    rows = [
        tx("2026-10-03", "purchase", "100.00", "LULULEMON ATHLETICA"),
        tx("2026-10-05", "deposit", "75.00", "PLATINUM LULULEMON CREDIT"),
        tx("2026-10-20", "deposit", "100.00", "LULULEMON"),
        tx("2026-10-22", "withdrawal", "75.00", "LULULEMON CREDIT REVERSAL"),
    ]
    result = run(rows, date(2026, 10, 25))
    kinds = {e["description"]: e["kind"] for e in evidence(result, "plat_lululemon")}
    assert kinds["LULULEMON"] == "merchant_refund"
    assert kinds["LULULEMON CREDIT REVERSAL"] == "credit_clawback"
    c = cur(result, "plat_lululemon")
    assert (c["used"], c["remaining"], c["pending"]) == ("0.00", "75.00", "0.00")


def test_07_refund_equal_to_purchase_over_cap(run):
    rows = [tx("2026-09-01", "purchase", "150.00", "LULULEMON ATHLETICA"), tx("2026-09-09", "deposit", "150.00", "LULULEMON.COM")]
    result = run(rows, date(2026, 9, 20))
    dep = [e for e in evidence(result, "plat_lululemon") if e["description"] == "LULULEMON.COM"][0]
    assert dep["kind"] == "merchant_refund" and dep["confidence"] == "high"


def test_08_credit_without_credit_words(run):
    rows = [tx("2026-10-01", "purchase", "150.00", "LULULEMON ATHLETICA"), tx("2026-10-03", "deposit", "75.00", "LULULEMON")]
    result = run(rows, date(2026, 10, 20))
    dep = [e for e in evidence(result, "plat_lululemon") if e["description"] == "LULULEMON"][0]
    assert dep["kind"] == "statement_credit" and dep["confidence"] == "medium"
    assert cur(result, "plat_lululemon")["used"] == "75.00"


def test_09_override_to_refund(run):
    rows = [tx("2026-10-01", "purchase", "150.00", "LULULEMON ATHLETICA", jid=501), tx("2026-10-03", "deposit", "75.00", "LULULEMON", jid=502)]
    overrides = {502: {"firefly_journal_id": 502, "classification": "merchant_refund", "benefit_id": None, "period_key": None}}
    c = cur(run(rows, date(2026, 10, 20), overrides=overrides), "plat_lululemon")
    assert (c["used"], c["pending"]) == ("0.00", "75.00")
    assert c["missing_credit"] is not None


def test_10_gift_card_not_eligible(run):
    rows = [tx("2026-10-02", "purchase", "50.00", "LULULEMON GIFT CARD")]
    result = run(rows, date(2026, 10, 20))
    c = cur(result, "plat_lululemon")
    assert (c["used"], c["pending"], c["remaining"]) == ("0.00", "0.00", "75.00")
    ev = evidence(result, "plat_lululemon")[0]
    assert ev["kind"] == "purchase" and "excluded" in (ev["note"] or "")


def test_11_digital_entertainment_partial(run):
    rows = [tx("2026-10-04", "deposit", "15.99", "PLATINUM DIGITAL ENT CREDIT")]
    c = cur(run(rows, date(2026, 10, 20)), "plat_digital_ent")
    assert (c["period_key"], c["used"], c["remaining"]) == ("2026-M10", "15.99", "9.01")


def test_12_uber_cash_manual(run):
    manual = {"plat_uber_cash": {"2026-M12": Decimal("35.00")}}
    result = run([], date(2026, 12, 15), manual=manual)
    dec = cur(result, "plat_uber_cash")
    assert (dec["cap"], dec["used"], dec["status"]) == ("35.00", "35.00", "used")
    nov = hist(result, "plat_uber_cash", "2026-M11")
    assert nov["status"] == "manual" and nov["cap"] == "15.00"


def test_13_saks_retired(run):
    result = run([], date(2026, 10, 20), year=2026)
    b = benefit(result, "plat_saks")
    assert b["current"] is None
    assert [h["period_key"] for h in b["history"]] == ["2026-H1"]


def test_14_resy_credits_only(run):
    rows = [tx("2026-10-14", "deposit", "100.00", "PLATINUM RESY CREDIT")]
    result = run(rows, date(2026, 10, 20))
    c = cur(result, "plat_resy")
    assert (c["period_key"], c["used"]) == ("2026-Q4", "100.00")
    assert evidence(result, "plat_resy")[0]["attribution"] == "by_credit_date"


def test_15_credit_attributed_to_purchase_period(run):
    rows = [tx("2026-09-28", "purchase", "80.00", "LULULEMON ATHLETICA"), tx("2026-10-02", "deposit", "75.00", "PLATINUM LULULEMON CREDIT")]
    result = run(rows, date(2026, 10, 20))
    credit = evidence(result, "plat_lululemon", "statement_credit")[0]
    assert credit["period_key"] == "2026-Q3" and credit["attribution"] == "by_purchase"
    assert hist(result, "plat_lululemon", "2026-Q3")["used"] == "75.00"
    assert cur(result, "plat_lululemon")["used"] == "0.00"


def test_16_over_cap(run):
    rows = [
        tx("2026-10-03", "purchase", "120.00", "LULULEMON ATHLETICA"),
        tx("2026-10-06", "deposit", "75.00", "PLATINUM LULULEMON CREDIT"),
        tx("2026-10-08", "deposit", "10.00", "PLATINUM LULULEMON CREDIT"),
    ]
    result = run(rows, date(2026, 10, 20))
    assert cur(result, "plat_lululemon")["used"] == "75.00"
    extra = [e for e in evidence(result, "plat_lululemon", "statement_credit") if e["amount"] == "10.00"][0]
    assert extra["over_cap"] is True and "over cap" in extra["note"]


def test_17_payment_ignored(run, engine):
    rows = [tx("2026-10-10", "payment", "500.00", "AMEX EPAYMENT ACH PMT")]
    result = run(rows, date(2026, 10, 20))
    for card in result["cards"]:
        for b in card["benefits"]:
            assert b["evidence"] == []
    assert engine.unclassified(result, date(2026, 10, 20)) == []


def test_18_unrecognized_deposit(run, engine):
    rows = [tx("2026-10-12", "deposit", "12.95", "AMEX CR 88231")]
    result = run(rows, date(2026, 10, 20))
    items = engine.unclassified(result, date(2026, 10, 20))
    assert len(items) == 1 and items[0]["description"] == "AMEX CR 88231" and items[0]["kind"] == "unclassified_deposit"


def test_gold_and_platinum_uber_one_do_not_conflict(run):
    rows = [tx("2026-10-08", "purchase", "9.99", "UBER ONE MEMBERSHIP", account="4"), tx("2026-10-11", "deposit", "9.99", "UBER ONE CREDIT", account="4")]
    result = run(rows, date(2026, 10, 20))
    assert cur(result, "gold_uber_one_promo")["used"] == "9.99"
    assert cur(result, "plat_uber_one")["used"] == "0.00"


def test_year_totals(run):
    rows = [tx("2026-10-03", "purchase", "120.00", "LULULEMON ATHLETICA"), tx("2026-10-06", "deposit", "75.00", "PLATINUM LULULEMON CREDIT")]
    result = run(rows, date(2026, 10, 20))
    plat = result["cards"][0]
    assert plat["captured_ytd"] == "75.00"
    assert abs(plat["fee_offset"] - 75 / 895) < 0.001
    # three expired lululemon quarters with nothing used plus other ended periods count as left on the table
    assert Decimal(plat["left_on_table_ytd"]) >= Decimal("225.00")


@freeze_time("2026-10-20 12:00:00")
def test_today_local_matches_frozen_clock():
    from app.util import today_local

    assert today_local() == date(2026, 10, 20)
