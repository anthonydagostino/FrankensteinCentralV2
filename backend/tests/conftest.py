from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("KIOSK_TOKEN", "kiosk-token-for-tests-1234567890")

from app.config_loader import get_benefits_catalog, get_dashboard_config  # noqa: E402
from app.services.benefits.engine import BenefitsEngine  # noqa: E402

PLAT = {"id": "3", "name": "Amex Platinum"}
GOLD = {"id": "4", "name": "Amex Gold"}
CARD_ACCOUNTS = {"amex_platinum": PLAT, "amex_gold": GOLD}

_jid = [100]


def tx(d: str, kind: str, amount: str, description: str, account: str = "3", jid: int | None = None, notes: str = "") -> dict:
    """kind: purchase | deposit | payment | withdrawal(other outflow)."""
    _jid[0] += 1
    jid = jid or _jid[0]
    acct_name = "Amex Platinum" if account == "3" else "Amex Gold"
    base = {"journal_id": jid, "group_id": str(9000 + jid), "date": d, "amount": amount, "description": description, "category_name": "", "budget_name": "", "tags": [], "notes": notes, "external_id": None, "currency_code": "USD"}
    if kind in ("purchase", "withdrawal"):
        base.update(type="withdrawal", source_id=account, source_name=acct_name, destination_id="500", destination_name="Merchant")
    elif kind == "deposit":
        base.update(type="deposit", source_id="600", source_name="American Express", destination_id=account, destination_name=acct_name)
    elif kind == "payment":
        base.update(type="transfer", source_id="1", source_name="Checking", destination_id=account, destination_name=acct_name)
    else:
        raise ValueError(kind)
    return base


@pytest.fixture(scope="session")
def engine() -> BenefitsEngine:
    return BenefitsEngine(get_benefits_catalog(), get_dashboard_config().cards)


@pytest.fixture
def run(engine):
    def _run(rows, today: date, year: int | None = None, overrides: dict | None = None, manual: dict | None = None):
        return engine.compute(rows, CARD_ACCOUNTS, overrides or {}, manual or {}, today, year or today.year)

    return _run


def benefit(result: dict, benefit_id: str) -> dict:
    for card in result["cards"]:
        for b in card["benefits"]:
            if b["id"] == benefit_id:
                return b
    raise KeyError(benefit_id)


def D(value) -> Decimal:
    return Decimal(str(value))


FIXTURES = Path(__file__).resolve().parent.parent / "app" / "fixtures"
