"""Recurring charge detector: finds subscriptions and other regular charges in Firefly withdrawals."""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..util import money, money_str

ZERO = Decimal("0.00")

# cadence name -> (nominal days, tolerance days)
CADENCES: list[tuple[str, int, int]] = [
    ("weekly", 7, 2),
    ("biweekly", 14, 3),
    ("monthly", 30, 5),
    ("bimonthly", 61, 8),
    ("quarterly", 91, 12),
    ("semiannual", 182, 16),
    ("annual", 365, 25),
]
STRICT_AMOUNT_CADENCES = {"weekly", "biweekly"}  # short cadences must repeat the exact amount
PER_YEAR = {"weekly": 52, "biweekly": 26, "monthly": 12, "bimonthly": 6, "quarterly": 4, "semiannual": 2, "annual": 1}
MIN_OCCURRENCES = {"weekly": 4, "biweekly": 3, "monthly": 2, "bimonthly": 2, "quarterly": 2, "semiannual": 2, "annual": 2}
AMOUNT_TOLERANCE = Decimal("0.20")  # 20 percent around the median still counts as "the same subscription"
VARIABLE_TOLERANCE = Decimal("0.60")  # utilities swing more; beyond this the cluster is noise
PRICE_INCREASE_MIN = Decimal("0.05")
NEW_WITHIN_DAYS = 60
LAPSED_AFTER_INTERVALS = 1.6

# payment processors whose descriptor hides the real merchant: split those clusters by amount
PASSTHROUGH = re.compile(r"(apple\.com/bill|apple\.com|itunes|paypal|pp\*|google \*|google\*|amzn digital|amazon digital|sq \*|sq\*|tst\*|venmo)", re.I)
NOISE_WORDS = {"inc", "llc", "ltd", "co", "com", "the", "online", "purchase", "payment", "pos", "debit", "card", "web", "www", "usa", "us", "nj", "ny"}


def normalize_key(description: str, destination: str | None = None) -> str:
    """Collapse a bank descriptor to a stable merchant key: upper case words without digits or store numbers."""
    text = (description or "").upper()
    text = re.sub(r"[*#]\s*\w+$", " ", text)  # trailing store or auth codes after * or #
    text = re.sub(r"\b\d[\d\-/.:]*\b", " ", text)  # any digit runs, dates, phone numbers
    text = re.sub(r"[^A-Z+& ]+", " ", text)
    words = [w for w in text.split() if w.lower() not in NOISE_WORDS and len(w) > 1]
    key = " ".join(words[:3])
    if not key and destination:
        key = re.sub(r"[^A-Z+& ]+", " ", destination.upper()).strip()
    return key or "(unknown)"


def classify_cadence(intervals: list[int]) -> tuple[str, int] | None:
    """Pick the cadence whose nominal interval most intervals agree with."""
    if not intervals:
        return None
    best: tuple[str, int, float] | None = None
    for name, nominal, tol in CADENCES:
        hits = sum(1 for i in intervals if abs(i - nominal) <= tol)
        share = hits / len(intervals)
        if share >= 0.6 and (best is None or share > best[2]):
            best = (name, nominal, share)
    if best is None:
        return None
    matching = [i for i in intervals if abs(i - best[1]) <= [t for n, _, t in CADENCES if n == best[0]][0]]
    return best[0], int(round(statistics.median(matching)))


def _within(a: Decimal, ref: Decimal, tol: Decimal) -> bool:
    if ref == 0:
        return a == 0
    return abs(a - ref) <= ref * tol


def detect(transactions: list[dict], today: date, ignored: set[str] | None = None, links: dict | None = None) -> dict:
    ignored = ignored or set()
    links = links or {}
    tmpl = links.get("transaction_template")
    clusters: dict[str, list[dict]] = defaultdict(list)
    for t in transactions:
        if t.get("type") != "withdrawal":
            continue
        desc = t.get("description") or ""
        key = normalize_key(desc, t.get("destination_name"))
        if PASSTHROUGH.search(desc):
            key = f"{key} {money_str(t['amount'])}"
        clusters[key].append(t)

    items: list[dict] = []
    for key, rows in clusters.items():
        rows.sort(key=lambda r: (r["date"], r["journal_id"]))
        # one charge per day per cluster: Firefly splits or duplicate imports should not create fake weekly cadence
        by_day: dict[str, dict] = {}
        for r in rows:
            by_day.setdefault(r["date"][:10], r)
        rows = list(by_day.values())
        if len(rows) < 2:
            continue
        dates = [date.fromisoformat(r["date"][:10]) for r in rows]
        intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
        cadence = classify_cadence(intervals)
        if cadence is None:
            continue
        name, interval = cadence
        if len(rows) < MIN_OCCURRENCES[name]:
            continue
        amounts = [money(r["amount"]) for r in rows]
        median = money(statistics.median(amounts))
        if name in STRICT_AMOUNT_CADENCES or len(rows) == 2:
            # short cadences, and clusters seen only twice, must repeat the exact amount to count
            if any(abs(a - median) > Decimal("0.01") for a in amounts):
                continue
            variable = False
        else:
            stable = sum(1 for a in amounts if _within(a, median, AMOUNT_TOLERANCE)) / len(amounts)
            loose = sum(1 for a in amounts if _within(a, median, VARIABLE_TOLERANCE)) / len(amounts)
            if stable >= 0.75:
                variable = False
            elif loose >= 0.85:
                variable = True
            else:
                continue
        last = rows[-1]
        last_date = dates[-1]
        next_expected = last_date + timedelta(days=interval)
        days_since = (today - last_date).days
        lapsed = days_since > interval * LAPSED_AFTER_INTERVALS
        is_new = (today - dates[0]).days <= NEW_WITHIN_DAYS
        # price increase: the latest amount is above the stable amount of earlier charges
        previous = money(statistics.median(amounts[:-1])) if len(amounts) > 1 else median
        increased = (not variable) and amounts[-1] > previous and (amounts[-1] - previous) >= previous * PRICE_INCREASE_MIN
        common_desc = Counter(r["description"] for r in rows).most_common(1)[0][0]
        annualized = amounts[-1] * Decimal(PER_YEAR[name])
        items.append(
            {
                "key": key,
                "name": common_desc.strip(),
                "merchant": last.get("destination_name") or None,
                "account": last.get("source_name") or None,
                "category": last.get("category_name") or None,
                "cadence": name,
                "interval_days": interval,
                "amount": money_str(amounts[-1]),
                "previous_amount": money_str(previous) if increased else None,
                "amount_min": money_str(min(amounts)),
                "amount_max": money_str(max(amounts)),
                "variable": variable,
                "occurrences": len(rows),
                "first_seen": dates[0].isoformat(),
                "last_seen": last_date.isoformat(),
                "next_expected": next_expected.isoformat(),
                "days_until_next": (next_expected - today).days,
                "monthly_cost": money_str(annualized / Decimal(12)),
                "annual_cost": money_str(annualized),
                "status": "lapsed" if lapsed else "active",
                "new": is_new,
                "price_increase": increased,
                "passthrough": bool(PASSTHROUGH.search(common_desc)),
                "ignored": key in ignored,
                "url": tmpl.format(group_id=last["group_id"]) if tmpl else None,
            }
        )

    items.sort(key=lambda i: (i["ignored"], i["status"] == "lapsed", -Decimal(i["monthly_cost"])))
    active = [i for i in items if i["status"] == "active" and not i["ignored"]]
    totals = {
        "monthly_total": money_str(sum((Decimal(i["monthly_cost"]) for i in active), ZERO)),
        "annual_total": money_str(sum((Decimal(i["annual_cost"]) for i in active), ZERO)),
        "active_count": len(active),
        "new_count": sum(1 for i in active if i["new"]),
        "increased_count": sum(1 for i in active if i["price_increase"]),
        "lapsed_count": sum(1 for i in items if i["status"] == "lapsed" and not i["ignored"]),
        "ignored_count": sum(1 for i in items if i["ignored"]),
    }
    return {"items": items, "totals": totals, "today": today.isoformat()}
