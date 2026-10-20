from __future__ import annotations

from datetime import date, timedelta

from app.services.recurring import classify_cadence, detect, normalize_key

_jid = [1]


def tx(d: date, amount: str, desc: str, kind: str = "withdrawal", dest: str = "Merchant", src: str = "Checking") -> dict:
    _jid[0] += 1
    return {"journal_id": _jid[0], "group_id": str(_jid[0]), "type": kind, "date": d.isoformat(), "amount": amount, "description": desc, "source_id": "1", "source_name": src, "destination_id": "9", "destination_name": dest, "category_name": "Subscriptions", "tags": [], "notes": ""}


def monthly(desc: str, amount: str, months: int, start: date = date(2026, 1, 3), amounts: list[str] | None = None) -> list[dict]:
    out = []
    for i in range(months):
        d = date(start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1, start.day)
        out.append(tx(d, amounts[i] if amounts else amount, desc))
    return out


TODAY = date(2026, 10, 20)


def test_normalize_key_strips_store_numbers_and_digits():
    assert normalize_key("DUNKIN #341209") == "DUNKIN"
    assert normalize_key("AMAZON.COM*MKTPL") == normalize_key("AMAZON.COM*MK7PL")
    assert normalize_key("APPLE.COM/BILL 866-712-7753") == "APPLE BILL"
    assert normalize_key("", "Netflix") == "NETFLIX"


def test_cadence_classification():
    assert classify_cadence([30, 31, 30, 29])[0] == "monthly"
    assert classify_cadence([7, 7, 8, 7])[0] == "weekly"
    assert classify_cadence([91, 92])[0] == "quarterly"
    assert classify_cadence([364])[0] == "annual"
    assert classify_cadence([3, 40, 9, 70]) is None


def test_monthly_subscription_detected_with_next_expected_and_costs():
    r = detect(monthly("NETFLIX.COM", "15.49", 10), TODAY)
    assert len(r["items"]) == 1
    item = r["items"][0]
    assert item["cadence"] == "monthly" and item["status"] == "active" and item["price_increase"] is False
    assert item["next_expected"] == "2026-11-03" and item["annual_cost"] == "185.88"
    assert r["totals"]["active_count"] == 1


def test_price_increase_flagged():
    amounts = ["15.49"] * 8 + ["17.99", "17.99"]
    r = detect(monthly("NETFLIX.COM", "15.49", 10, amounts=amounts), TODAY)
    item = r["items"][0]
    assert item["price_increase"] is True and item["previous_amount"] == "15.49" and item["amount"] == "17.99"
    assert r["totals"]["increased_count"] == 1


def test_lapsed_subscription():
    r = detect(monthly("SPOTIFY USA", "11.99", 6), TODAY)  # Jan to Jun, nothing since
    item = r["items"][0]
    assert item["status"] == "lapsed" and r["totals"]["lapsed_count"] == 1 and r["totals"]["active_count"] == 0


def test_new_subscription_with_two_exact_charges():
    rows = [tx(date(2026, 9, 14), "4.00", "NYTIMES*NYT DIGITAL"), tx(date(2026, 10, 14), "4.00", "NYTIMES*NYT DIGITAL")]
    r = detect(rows, TODAY)
    assert len(r["items"]) == 1 and r["items"][0]["new"] is True
    # two charges with different amounts are not enough evidence
    rows[1]["amount"] = "5.00"
    assert detect(rows, TODAY)["items"] == []


def test_variable_utility_kept_but_groceries_dropped():
    utility = monthly("JCP&L ELECTRIC", "90.00", 10, amounts=["60.00", "140.00", "75.00", "130.00", "95.00", "120.00", "70.00", "135.00", "88.00", "110.00"])
    r = detect(utility, TODAY)
    assert len(r["items"]) == 1 and r["items"][0]["variable"] is True
    weekly = [tx(date(2026, 8, 1) + timedelta(days=7 * i), f"{40 + i * 3}.00", "WEGMANS OCEAN NJ") for i in range(10)]
    assert detect(weekly, TODAY)["items"] == []
    exact_weekly = [tx(date(2026, 8, 1) + timedelta(days=7 * i), "12.00", "GYM CLASS") for i in range(10)]
    assert detect(exact_weekly, TODAY)["items"][0]["cadence"] == "weekly"


def test_passthrough_processor_split_by_amount():
    rows = monthly("APPLE.COM/BILL 866-712-7753", "2.99", 6) + monthly("APPLE.COM/BILL 866-712-7753", "9.99", 6, start=date(2026, 1, 21))
    r = detect(rows, TODAY)
    assert len(r["items"]) == 2 and all(i["passthrough"] for i in r["items"])


def test_transfers_deposits_and_ignored_keys_excluded():
    rows = monthly("AMEX EPAYMENT ACH PMT", "500.00", 6) 
    for r in rows:
        r["type"] = "transfer"
    assert detect(rows, TODAY)["items"] == []
    subs = monthly("NETFLIX.COM", "15.49", 10)
    r = detect(subs, TODAY, ignored={"NETFLIX"})
    assert r["items"][0]["ignored"] is True and r["totals"]["active_count"] == 0 and r["totals"]["ignored_count"] == 1
