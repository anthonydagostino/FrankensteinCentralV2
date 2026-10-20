from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import require_read, require_write
from ..deps import get_state
from ..integrations.firefly import trigger_importer
from ..services.finance import firefly_links, recent_transactions
from ..state import AppState

log = logging.getLogger("frankenstein.routes.finance")
router = APIRouter(prefix="/api", tags=["finance"], dependencies=[Depends(require_read)])


def _firefly_env(state: AppState, builder):
    env = state.cache.envelope("firefly")
    env["module"] = "finance"
    if env.get("data") is not None:
        try:
            env["data"] = builder()
        except Exception as exc:
            log.exception("finance view failed")
            env["status"] = "error"
            env["error"] = f"Could not derive finance view: {exc.__class__.__name__}"
            env["data"] = None
    return env


@router.get("/finance/summary")
async def finance_summary(state: AppState = Depends(get_state)):
    return _firefly_env(state, state.finance_summary)


@router.get("/finance/transactions")
async def finance_transactions(limit: int = Query(15, ge=1, le=100), state: AppState = Depends(get_state)):
    def build():
        data = state.firefly_data() or {}
        return {"transactions": recent_transactions(data.get("transactions") or [], firefly_links(state.settings.firefly_vanity_url), limit)}

    return _firefly_env(state, build)


@router.get("/finance/recurring")
async def finance_recurring(state: AppState = Depends(get_state)):
    env = _firefly_env(state, state.recurring)
    env["module"] = "recurring"
    return env


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

    async def later():
        await asyncio.sleep(90)
        state.scheduler.trigger("firefly")

    asyncio.create_task(later())
    return {"ok": result["ok"], "importer_status": result["status_code"], "refresh_in_seconds": 90}


@router.get("/cards")
async def cards(state: AppState = Depends(get_state)):
    env = state.cache.envelope("firefly")
    env["module"] = "cards"
    if env.get("data") is not None:
        try:
            env["data"] = state.cards()
        except Exception as exc:
            log.exception("cards view failed")
            env["status"] = "error"
            env["error"] = f"Could not derive card view: {exc.__class__.__name__}"
            env["data"] = None
    return env
