from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import require_read, require_write
from ..deps import get_state
from ..services.benefits.classify import suggest_pattern
from ..state import AppState
from ..util import iso, today_local, utcnow

log = logging.getLogger("frankenstein.routes.benefits")
router = APIRouter(prefix="/api/benefits", tags=["benefits"], dependencies=[Depends(require_read)])


def _env(state: AppState, builder):
    env = state.cache.envelope("firefly")
    env["module"] = "benefits"
    if env.get("data") is not None:
        try:
            env["data"] = builder()
        except Exception as exc:
            log.exception("benefits view failed")
            env["status"] = "error"
            env["error"] = f"Could not compute benefits: {exc.__class__.__name__}"
            env["data"] = None
    return env


@router.get("")
async def benefits(year: int | None = Query(None, ge=2020, le=2100), state: AppState = Depends(get_state)):
    return _env(state, lambda: state.benefits_public(year))


@router.get("/unclassified")
async def unclassified(days: int = Query(120, ge=1, le=400), state: AppState = Depends(get_state)):
    def build():
        result = state.benefits()
        rows = state.engine.unclassified(result, today_local(), days) if result else []
        for r in rows:
            r["suggested_pattern"] = suggest_pattern(r["description"])
        overrides = [dict(o) for o in state.db.fetchall("SELECT * FROM benefit_overrides ORDER BY created_at DESC")]
        return {"items": rows, "overrides": overrides, "benefits": [{"id": b.id, "name": b.name, "card": b.card} for b in state.engine.benefits]}

    return _env(state, build)


class OverrideBody(BaseModel):
    journal_id: int
    classification: Literal["statement_credit", "merchant_refund", "payment", "ignore", "purchase", "credit_clawback"]
    benefit_id: str | None = None
    period_key: str | None = None
    note: str | None = None


@router.post("/overrides", dependencies=[Depends(require_write)])
async def save_override(body: OverrideBody, state: AppState = Depends(get_state)):
    if body.classification in ("statement_credit", "purchase", "credit_clawback") and not body.benefit_id:
        raise HTTPException(status_code=400, detail="benefit_id is required for this classification")
    if body.benefit_id and body.benefit_id not in {b.id for b in state.engine.benefits}:
        raise HTTPException(status_code=400, detail="Unknown benefit id")
    state.db.execute(
        "INSERT INTO benefit_overrides(firefly_journal_id, classification, benefit_id, period_key, note, created_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(firefly_journal_id) DO UPDATE SET classification=excluded.classification, benefit_id=excluded.benefit_id, period_key=excluded.period_key, note=excluded.note, created_at=excluded.created_at",
        (body.journal_id, body.classification, body.benefit_id, body.period_key, body.note, iso(utcnow())),
    )
    state.invalidate_benefits()
    row = state.db.fetchone("SELECT * FROM benefit_overrides WHERE firefly_journal_id = ?", (body.journal_id,))
    await _maybe_writeback(state, body)
    return {"ok": True, "override": dict(row) if row else None}


@router.delete("/overrides/{override_id}", dependencies=[Depends(require_write)])
async def delete_override(override_id: int, state: AppState = Depends(get_state)):
    state.db.execute("DELETE FROM benefit_overrides WHERE id = ?", (override_id,))
    state.invalidate_benefits()
    return {"ok": True}


class ManualBody(BaseModel):
    benefit_id: str
    period_key: str
    amount: str | None = None  # None or "" means "used, full cap"
    used: bool = True
    note: str | None = None


@router.post("/manual", dependencies=[Depends(require_write)])
async def manual_usage(body: ManualBody, state: AppState = Depends(get_state)):
    benefit = next((b for b in state.engine.benefits if b.id == body.benefit_id), None)
    if benefit is None:
        raise HTTPException(status_code=400, detail="Unknown benefit id")
    if not body.used:
        state.db.execute("DELETE FROM benefit_manual_usage WHERE benefit_id = ? AND period_key = ?", (body.benefit_id, body.period_key))
        state.invalidate_benefits()
        return {"ok": True, "removed": True}
    if body.amount in (None, ""):
        from ..services.benefits.periods import cap_for, period_for

        try:
            sample = _period_sample_date(body.period_key)
            amount = cap_for(benefit, period_for(benefit.period, sample))
        except ValueError:
            amount = benefit.cap
    else:
        try:
            amount = Decimal(str(body.amount)).quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise HTTPException(status_code=400, detail="amount must be a number") from exc
        if amount < 0:
            raise HTTPException(status_code=400, detail="amount must be positive")
    state.db.execute(
        "INSERT INTO benefit_manual_usage(benefit_id, period_key, amount, note, created_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(benefit_id, period_key) DO UPDATE SET amount=excluded.amount, note=excluded.note, created_at=excluded.created_at",
        (body.benefit_id, body.period_key, f"{amount:.2f}", body.note, iso(utcnow())),
    )
    state.invalidate_benefits()
    return {"ok": True, "amount": f"{amount:.2f}"}


def _period_sample_date(key: str):
    from datetime import date

    year = int(key[:4])
    if "-M" in key:
        return date(year, int(key.split("-M")[1]), 1)
    if "-Q" in key:
        return date(year, 3 * (int(key.split("-Q")[1]) - 1) + 1, 1)
    if "-H" in key:
        return date(year, 1 if key.endswith("H1") else 7, 1)
    return date(year, 1, 1)


async def _maybe_writeback(state: AppState, body: OverrideBody) -> None:
    if not state.settings.firefly_writeback_tags or body.classification != "statement_credit":
        return
    integration = state.integrations.get("firefly")
    if integration is None or integration.is_mocked() or not integration.is_configured():
        return
    data = state.firefly_data() or {}
    row = next((t for t in data.get("transactions") or [] if int(t.get("journal_id") or 0) == body.journal_id), None)
    if not row:
        return
    from ..integrations.firefly import add_tags_to_group

    tags = ["amex-credit", f"benefit:{body.benefit_id}" + (f":{body.period_key}" if body.period_key else "")]
    try:
        await add_tags_to_group(state.settings, row["group_id"], body.journal_id, tags)
    except Exception as exc:
        log.warning("tag write back failed: %s", exc.__class__.__name__)
