"""Generate the Firefly III API shaped fixture (anchored on 2026-10-20).

Run: python -m app.fixtures.generate_firefly
The mock() of the Firefly integration shifts every date by (today - anchor).
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANCHOR = date(2026, 10, 20)
START = date(2025, 11, 1)

ACCOUNTS = [
    # id, name, type, role, balance, liability_type
    (1, "Chase Checking", "asset", "defaultAsset", "4312.77", None),
    (2, "Ally Savings", "asset", "savingAsset", "18250.00", None),
    (3, "Amex Platinum", "asset", "ccAsset", "-1842.19", None),
    (4, "Amex Gold", "asset", "ccAsset", "-612.40", None),
    (5, "Discover It", "asset", "ccAsset", "-233.15", None),
    (6, "Student Loan", "liabilities", None, "-14500.00", "loan"),
]
ACCOUNT_NAME = {a[0]: a[1] for a in ACCOUNTS}
ACCOUNT_TYPE = {a[0]: ("Asset account" if a[2] == "asset" else "Loan") for a in ACCOUNTS}

_expense_ids: dict[str, int] = {}
_revenue_ids: dict[str, int] = {}


def expense_id(name: str) -> int:
    if name not in _expense_ids:
        _expense_ids[name] = 100 + len(_expense_ids)
    return _expense_ids[name]


def revenue_id(name: str) -> int:
    if name not in _revenue_ids:
        _revenue_ids[name] = 300 + len(_revenue_ids)
    return _revenue_ids[name]


rows: list[dict] = []
_jid = 1000


def add(day: date, kind: str, amount: str, description: str, *, src: int | str, dst: int | str, category: str = "", budget: str = "", tags=None, notes: str = ""):
    """src/dst: int for an asset/liability account id, str for an expense or revenue account name."""
    global _jid
    if day < START or day > ANCHOR:
        return
    _jid += 1
    if kind == "withdrawal":
        source_id, source_name, source_type = src, ACCOUNT_NAME[src], ACCOUNT_TYPE[src]
        destination_id, destination_name, destination_type = expense_id(dst), dst, "Expense account"
    elif kind == "deposit":
        source_id, source_name, source_type = revenue_id(src), src, "Revenue account"
        destination_id, destination_name, destination_type = dst, ACCOUNT_NAME[dst], ACCOUNT_TYPE[dst]
    else:
        source_id, source_name, source_type = src, ACCOUNT_NAME[src], ACCOUNT_TYPE[src]
        destination_id, destination_name, destination_type = dst, ACCOUNT_NAME[dst], ACCOUNT_TYPE[dst]
    rows.append(
        {
            "user": "1",
            "transaction_journal_id": str(_jid),
            "type": kind,
            "date": f"{day.isoformat()}T00:00:00-04:00",
            "order": 0,
            "currency_id": "1",
            "currency_code": "USD",
            "currency_symbol": "$",
            "currency_decimal_places": 2,
            "amount": f"{Decimal(amount):.6f}",
            "description": description,
            "source_id": str(source_id),
            "source_name": source_name,
            "source_type": source_type,
            "destination_id": str(destination_id),
            "destination_name": destination_name,
            "destination_type": destination_type,
            "budget_id": None,
            "budget_name": budget or None,
            "category_id": None,
            "category_name": category or None,
            "tags": tags or [],
            "notes": notes or None,
            "external_id": f"simplefin-{_jid}" if src in (3, 4, 5) or dst in (3, 4, 5) else None,
            "reconciled": False,
        }
    )


def months():
    d = date(START.year, START.month, 1)
    while d <= ANCHOR:
        yield d
        d = (d + timedelta(days=32)).replace(day=1)


def build() -> dict:
    rnd = random.Random(7)
    PLAT, GOLD, DISC, CHK, SAV, LOAN = 3, 4, 5, 1, 2, 6

    for m in months():
        y, mo = m.year, m.month

        def dt(day: int) -> date:
            return date(y, mo, min(day, 28))

        # Checking: payroll, rent, utilities, savings transfer, loan payment
        add(dt(1), "deposit", "3450.00", "PAYROLL ACME CORP", src="Acme Corp", dst=CHK, category="Salary")
        add(dt(15), "deposit", "3450.00", "PAYROLL ACME CORP", src="Acme Corp", dst=CHK, category="Salary")
        add(dt(1), "withdrawal", "1850.00", "RENT PAYMENT", src=CHK, dst="Landlord", category="Housing", budget="Housing")
        add(dt(12), "withdrawal", "94.60", "JCP&L ELECTRIC", src=CHK, dst="JCP&L", category="Utilities", budget="Utilities")
        add(dt(18), "withdrawal", "85.00", "VERIZON WIRELESS", src=CHK, dst="Verizon", category="Utilities", budget="Utilities")
        add(dt(3), "withdrawal", "15.49", "NETFLIX.COM", src=CHK, dst="Netflix", category="Subscriptions")
        add(dt(16), "transfer", "500.00", "Transfer to savings", src=CHK, dst=SAV)
        add(dt(20), "transfer", "220.00", "Student loan payment", src=CHK, dst=LOAN)

        # Platinum: monthly benefits
        add(dt(4), "withdrawal", "15.99", "DISNEY PLUS", src=PLAT, dst="Disney Plus", category="Subscriptions")
        add(dt(7), "deposit", "15.99", "PLATINUM DIGITAL ENT CREDIT", src="American Express", dst=PLAT, category="Statement credit")
        add(dt(10), "withdrawal", "13.81", "WALMART+ MEMBERSHIP", src=PLAT, dst="Walmart", category="Subscriptions")
        add(dt(13), "deposit", "13.81", "WALMART PLUS CREDIT", src="American Express", dst=PLAT, category="Statement credit")
        add(dt(8), "withdrawal", "9.99", "UBER ONE MEMBERSHIP", src=PLAT, dst="Uber", category="Subscriptions")
        add(dt(11), "deposit", "9.99", "UBER ONE CREDIT", src="American Express", dst=PLAT, category="Statement credit")
        # Platinum: everyday spend
        for _ in range(3):
            add(dt(rnd.randint(2, 27)), "withdrawal", f"{rnd.uniform(38, 140):.2f}", "WEGMANS OCEAN NJ", src=PLAT, dst="Wegmans", category="Groceries", budget="Groceries")
        for _ in range(2):
            add(dt(rnd.randint(2, 27)), "withdrawal", f"{rnd.uniform(22, 95):.2f}", "AMAZON.COM*MKTPL", src=PLAT, dst="Amazon", category="Shopping", budget="Shopping")
        add(dt(rnd.randint(2, 27)), "withdrawal", f"{rnd.uniform(60, 180):.2f}", "COSTCO WHSE #0233", src=PLAT, dst="Costco", category="Groceries", budget="Groceries")
        add(dt(rnd.randint(2, 27)), "withdrawal", f"{rnd.uniform(45, 110):.2f}", "SHELL OIL 574", src=PLAT, dst="Shell", category="Gas", budget="Gas")
        # Platinum payment
        add(dt(25), "transfer", f"{rnd.uniform(1400, 2600):.2f}", "AMEX EPAYMENT ACH PMT", src=CHK, dst=PLAT)

        # Gold: dining and Dunkin
        if (y, mo) < (2026, 10):
            add(dt(6), "withdrawal", "23.40", "GRUBHUB", src=GOLD, dst="Grubhub", category="Dining", budget="Dining")
            add(dt(9), "deposit", "10.00", "GOLD DINING CREDIT", src="American Express", dst=GOLD, category="Statement credit")
            add(dt(2), "withdrawal", "4.85", "DUNKIN #341209", src=GOLD, dst="Dunkin", category="Dining", budget="Dining")
            add(dt(15), "withdrawal", "5.10", "DUNKIN #341209", src=GOLD, dst="Dunkin", category="Dining", budget="Dining")
            add(dt(18), "deposit", "7.00", "DUNKIN CREDIT", src="American Express", dst=GOLD, category="Statement credit")
        for _ in range(4):
            add(dt(rnd.randint(2, 27)), "withdrawal", f"{rnd.uniform(18, 88):.2f}", rnd.choice(["CHIPOTLE 2210", "SURF TACO TOMS RIVER", "XINA RESTAURANT", "BUBBAKOO'S BURRITOS"]), src=GOLD, dst="Restaurants", category="Dining", budget="Dining")
        for _ in range(2):
            add(dt(rnd.randint(2, 27)), "withdrawal", f"{rnd.uniform(40, 120):.2f}", "SHOPRITE TOMS RIVER", src=GOLD, dst="ShopRite", category="Groceries", budget="Groceries")
        add(dt(24), "transfer", f"{rnd.uniform(350, 800):.2f}", "AMEX EPAYMENT ACH PMT", src=CHK, dst=GOLD)

        # Discover
        add(dt(rnd.randint(2, 27)), "withdrawal", f"{rnd.uniform(40, 70):.2f}", "WAWA 8120", src=DISC, dst="Wawa", category="Gas", budget="Gas")
        add(dt(rnd.randint(2, 27)), "withdrawal", f"{rnd.uniform(25, 90):.2f}", "TARGET 00021", src=DISC, dst="Target", category="Shopping", budget="Shopping")
        add(dt(23), "transfer", f"{rnd.uniform(120, 260):.2f}", "DISCOVER E-PAYMENT", src=CHK, dst=DISC)

    # Quarterly lululemon (Platinum)
    add(date(2026, 1, 15), "withdrawal", "98.50", "LULULEMON ATHLETICA", src=PLAT, dst="lululemon", category="Clothing", budget="Shopping")
    add(date(2026, 1, 18), "deposit", "75.00", "PLATINUM LULULEMON CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 4, 9), "withdrawal", "120.00", "LULULEMON.COM", src=PLAT, dst="lululemon", category="Clothing", budget="Shopping")
    add(date(2026, 4, 12), "deposit", "75.00", "PLATINUM LULULEMON CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 7, 20), "withdrawal", "64.00", "LULULEMON ATHLETICA", src=PLAT, dst="lululemon", category="Clothing", budget="Shopping")
    add(date(2026, 7, 23), "deposit", "64.00", "PLATINUM LULULEMON CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 10, 3), "withdrawal", "120.00", "LULULEMON ATHLETICA", src=PLAT, dst="lululemon", category="Clothing", budget="Shopping")
    add(date(2026, 10, 6), "deposit", "75.00", "PLATINUM LULULEMON CREDIT", src="American Express", dst=PLAT, category="Statement credit")

    # Resy (Platinum, credits only)
    add(date(2026, 2, 14), "withdrawal", "143.20", "ROSEMARY'S WEST VILLAGE", src=PLAT, dst="Restaurants", category="Dining", budget="Dining")
    add(date(2026, 2, 20), "deposit", "100.00", "PLATINUM RESY CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 5, 11), "deposit", "100.00", "PLATINUM RESY CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 8, 30), "deposit", "100.00", "PLATINUM RESY CREDIT", src="American Express", dst=PLAT, category="Statement credit")

    # CLEAR, hotel, airline, Saks, Global Entry (Platinum)
    add(date(2026, 2, 2), "withdrawal", "219.00", "CLEARME.COM", src=PLAT, dst="CLEAR", category="Travel")
    add(date(2026, 2, 5), "deposit", "219.00", "CLEAR PLUS CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 3, 14), "withdrawal", "540.00", "AMEX TRAVEL FHR PREPAID", src=PLAT, dst="Amex Travel", category="Travel")
    add(date(2026, 3, 20), "deposit", "300.00", "AMEX TRAVEL HOTEL CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 6, 5), "withdrawal", "35.00", "UNITED AIRLINES BAG FEE", src=PLAT, dst="United Airlines", category="Travel")
    add(date(2026, 6, 9), "deposit", "35.00", "AIRLINE FEE CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 9, 2), "withdrawal", "70.00", "UNITED AIRLINES BAG FEE", src=PLAT, dst="United Airlines", category="Travel")
    add(date(2026, 9, 6), "deposit", "70.00", "AIRLINE FEE CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 1, 22), "withdrawal", "62.00", "SAKS FIFTH AVENUE", src=PLAT, dst="Saks", category="Clothing", budget="Shopping")
    add(date(2026, 1, 25), "deposit", "50.00", "SAKS CREDIT", src="American Express", dst=PLAT, category="Statement credit")
    add(date(2026, 3, 3), "withdrawal", "120.00", "US CUSTOMS CBP GLOBAL ENTRY", src=PLAT, dst="US CBP", category="Travel")
    add(date(2026, 3, 6), "deposit", "120.00", "GLOBAL ENTRY CREDIT", src="American Express", dst=PLAT, category="Statement credit")

    # Unclassified and refund deposits (Discovery screen)
    add(date(2026, 10, 12), "deposit", "12.95", "AMEX CR 88231", src="American Express", dst=PLAT)
    add(date(2026, 9, 14), "deposit", "34.99", "AMAZON.COM REFUND", src="Amazon", dst=PLAT)

    # Gold, October: Grubhub with pending credit, Dunkin partial
    add(date(2026, 10, 17), "withdrawal", "18.20", "GRUBHUB", src=GOLD, dst="Grubhub", category="Dining", budget="Dining")
    add(date(2026, 10, 2), "withdrawal", "4.85", "DUNKIN #341209", src=GOLD, dst="Dunkin", category="Dining", budget="Dining")
    add(date(2026, 10, 5), "deposit", "4.85", "DUNKIN CREDIT", src="American Express", dst=GOLD, category="Statement credit")
    # Fresh card activity so the mock never looks stale
    add(date(2026, 10, 20), "withdrawal", "47.18", "WAWA 8120", src=PLAT, dst="Wawa", category="Gas", budget="Gas")
    add(date(2026, 10, 19), "withdrawal", "6.45", "STARBUCKS 09821", src=GOLD, dst="Starbucks", category="Dining", budget="Dining")
    add(date(2026, 10, 19), "withdrawal", "31.70", "TARGET 00021", src=DISC, dst="Target", category="Shopping", budget="Shopping")
    # Gold Resy H1
    add(date(2026, 3, 9), "deposit", "50.00", "GOLD RESY CREDIT", src="American Express", dst=GOLD, category="Statement credit")

    rows.sort(key=lambda r: (r["date"], int(r["transaction_journal_id"])))

    groups = []
    for idx, r in enumerate(rows):
        groups.append({"type": "transactions", "id": str(5000 + idx), "attributes": {"created_at": r["date"], "updated_at": r["date"], "user": "1", "group_title": None, "transactions": [r]}, "links": {"self": f"/api/v1/transactions/{5000 + idx}"}})

    accounts = []
    for aid, name, atype, role, balance, ltype in ACCOUNTS:
        accounts.append(
            {
                "type": "accounts",
                "id": str(aid),
                "attributes": {
                    "active": True,
                    "name": name,
                    "type": atype,
                    "account_role": role,
                    "liability_type": ltype,
                    "currency_code": "USD",
                    "current_balance": f"{Decimal(balance):.6f}",
                    "current_balance_date": f"{ANCHOR.isoformat()}T00:00:00-04:00",
                    "virtual_balance": "0.000000",
                    "include_net_worth": True,
                    "notes": None,
                },
            }
        )

    # Month to date aggregates for insights and budgets
    month_start = ANCHOR.replace(day=1)
    cat_totals: dict[str, Decimal] = defaultdict(Decimal)
    merch_totals: dict[str, Decimal] = defaultdict(Decimal)
    budget_totals: dict[str, Decimal] = defaultdict(Decimal)
    spent_total = Decimal("0")
    earned_total = Decimal("0")
    for r in rows:
        d = date.fromisoformat(r["date"][:10])
        if d < month_start:
            continue
        amt = Decimal(r["amount"])
        if r["type"] == "withdrawal":
            spent_total += amt
            cat_totals[r["category_name"] or "(no category)"] += amt
            merch_totals[r["destination_name"]] += amt
            if r["budget_name"]:
                budget_totals[r["budget_name"]] += amt
        elif r["type"] == "deposit":
            earned_total += amt

    net_worth = sum(Decimal(a[4]) for a in ACCOUNTS)
    summary = {
        "net-worth-in-USD": {"key": "net-worth-in-USD", "title": "Net worth in USD", "monetary_value": f"{net_worth:.2f}", "currency_code": "USD", "value_parsed": f"${net_worth:,.2f}"},
        "spent-in-USD": {"key": "spent-in-USD", "title": "Spent in USD", "monetary_value": f"{-spent_total:.2f}", "currency_code": "USD", "value_parsed": f"-${spent_total:,.2f}"},
        "earned-in-USD": {"key": "earned-in-USD", "title": "Earned in USD", "monetary_value": f"{earned_total:.2f}", "currency_code": "USD", "value_parsed": f"${earned_total:,.2f}"},
        "bills-unpaid-in-USD": {"key": "bills-unpaid-in-USD", "title": "Bills unpaid", "monetary_value": "195.49", "currency_code": "USD", "value_parsed": "$195.49"},
        "left-to-spend-in-USD": {"key": "left-to-spend-in-USD", "title": "Left to spend", "monetary_value": f"{Decimal('1500.00') - budget_totals.get('Groceries', Decimal(0)) - budget_totals.get('Dining', Decimal(0)) - budget_totals.get('Gas', Decimal(0)) - budget_totals.get('Shopping', Decimal(0)):.2f}", "currency_code": "USD", "value_parsed": ""},
    }

    insight_category = [{"id": str(i + 1), "name": k, "difference": f"{-v:.2f}", "difference_float": float(-v), "currency_id": "1", "currency_code": "USD"} for i, (k, v) in enumerate(sorted(cat_totals.items(), key=lambda kv: -kv[1]))]
    insight_expense = [{"id": str(expense_id(k)), "name": k, "difference": f"{-v:.2f}", "difference_float": float(-v), "currency_id": "1", "currency_code": "USD"} for k, v in sorted(merch_totals.items(), key=lambda kv: -kv[1])]

    budget_defs = [("1", "Groceries", "600.00"), ("2", "Dining", "400.00"), ("3", "Gas", "200.00"), ("4", "Shopping", "300.00"), ("5", "Housing", "1850.00"), ("6", "Utilities", "200.00")]
    budgets = {"data": [{"type": "budgets", "id": bid, "attributes": {"active": True, "name": name, "spent": []}} for bid, name, _ in budget_defs]}
    budget_limits = {
        bid: [{"type": "budget_limits", "id": f"9{bid}", "attributes": {"budget_id": bid, "start": month_start.isoformat(), "end": ANCHOR.replace(day=28).isoformat(), "amount": limit, "spent": f"{-budget_totals.get(name, Decimal(0)):.2f}", "currency_code": "USD"}}]
        for bid, name, limit in budget_defs
    }

    bills = {
        "data": [
            {"type": "bills", "id": "1", "attributes": {"active": True, "name": "Rent", "amount_min": "1850.00", "amount_max": "1850.00", "repeat_freq": "monthly", "next_expected_match": "2026-11-01T00:00:00-04:00", "pay_dates": ["2026-11-01T00:00:00-04:00"], "paid_dates": []}},
            {"type": "bills", "id": "2", "attributes": {"active": True, "name": "Verizon Wireless", "amount_min": "85.00", "amount_max": "85.00", "repeat_freq": "monthly", "next_expected_match": "2026-10-28T00:00:00-04:00", "pay_dates": ["2026-10-28T00:00:00-04:00"], "paid_dates": []}},
            {"type": "bills", "id": "3", "attributes": {"active": True, "name": "JCP&L Electric", "amount_min": "80.00", "amount_max": "110.00", "repeat_freq": "monthly", "next_expected_match": "2026-10-30T00:00:00-04:00", "pay_dates": ["2026-10-30T00:00:00-04:00"], "paid_dates": []}},
            {"type": "bills", "id": "4", "attributes": {"active": True, "name": "Netflix", "amount_min": "15.49", "amount_max": "15.49", "repeat_freq": "monthly", "next_expected_match": "2026-11-03T00:00:00-04:00", "pay_dates": ["2026-11-03T00:00:00-04:00"], "paid_dates": []}},
            {"type": "bills", "id": "5", "attributes": {"active": True, "name": "Car insurance", "amount_min": "142.00", "amount_max": "142.00", "repeat_freq": "monthly", "next_expected_match": "2026-11-15T00:00:00-04:00", "pay_dates": ["2026-11-15T00:00:00-04:00"], "paid_dates": []}},
        ]
    }

    return {
        "_anchor": ANCHOR.isoformat(),
        "about": {"data": {"version": "6.1.25", "api_version": "2.1.0", "php_version": "8.3.12", "os": "Linux", "driver": "mysql"}},
        "accounts": {"data": accounts, "meta": {"pagination": {"total": len(accounts), "count": len(accounts), "per_page": 100, "current_page": 1, "total_pages": 1}}},
        "summary": summary,
        "transactions": {"data": groups, "meta": {"pagination": {"total": len(groups), "count": len(groups), "per_page": 1000, "current_page": 1, "total_pages": 1}}},
        "insight_category": insight_category,
        "insight_expense": insight_expense,
        "budgets": budgets,
        "budget_limits": budget_limits,
        "bills": bills,
    }


if __name__ == "__main__":
    (HERE / "firefly").mkdir(exist_ok=True)
    data = build()
    (HERE / "firefly" / "firefly.json").write_text(json.dumps(data, indent=1))
    print(f"firefly fixture written: {len(data['transactions']['data'])} transaction groups")
