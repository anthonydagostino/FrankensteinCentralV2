"""Finance, cards, and recurring charge routes, all derived from the Firefly cache."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import require_read, require_write
from ..deps import get_state
from ..integrations.firefly import trigger_importer
from ..services.finance import firefly_links, recent_transactions
from ..state import AppState

router = APIRouter(prefix="/api", tags=["finance"], dependencies=[Depends(require_read)])


@router.get("/finance/summary")
async def finance_summary(state: AppState = Depends(get_state)):
    return state.derived_envelope("finance", state.finance_summary)


@router.get("/finance/transactions")
async def finance_transactions(limit: int = Query(15, ge=1, le=100), state: AppState = Depends(get_state)):
    def build():
        data = state.firefly_data() or {}
        return {"transactions": recent_transactions(data.get("transactions") or [], firefly_links(state.settings.firefly_vanity_url), limit)}

    return state.derived_envelope("finance", build)


@router.get("/finance/recurring")
async def finance_recurring(state: AppState = Depends(get_state)):
    return state.derived_envelope("recurring", state.recurring)


class IgnoreBody(BaseModel):
    key: str
    ignore: bool = True


@router.post("/finance/recurring/ignore", dependencies=[Depends(require_write)])
async def finance_recurring_ignore(body: IgnoreBody, state: AppState = Depends(get_state)):
    if not body.key or len(body.key) > 120:
        raise HTTPException(status_code=400, detail="key is required")
    keys = state.set_recurring_ignored(body.key, body.ignore)
    return {"ok": True, "ignored": sorted(keys)}


@router.post("/finance/sync", dependencies=[Depends(require_write)])
async def finance_sync(state: AppState = Depends(get_state)):
    s = state.settings
    if not (s.firefly_importer_url and s.firefly_importer_secret):
        raise HTTPException(status_code=400, detail="Set FIREFLY_IMPORTER_URL and FIREFLY_IMPORTER_SECRET to enable Sync now")
    integration = state.integrations.get("firefly")
    if integration is not None and integration.is_mocked():
        state.scheduler.trigger("firefly")
        return {"ok": True, "mocked": True}
    try:
        result = await trigger_importer(s)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Importer unreachable: {exc.__class__.__name__}") from exc

    async def refresh_after_import():
        await asyncio.sleep(90)
        state.scheduler.trigger("firefly")

    state.spawn(refresh_after_import())
    return {"ok": result["ok"], "importer_status": result["status_code"], "refresh_in_seconds": 90}


@router.get("/cards")
async def cards(state: AppState = Depends(get_state)):
    return state.derived_envelope("cards", state.cards)
