from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..auth import require_read, require_write
from ..deps import get_state
from ..state import AppState
from ..util import iso, utcnow

router = APIRouter(prefix="/api", tags=["core"])


@router.get("/health")
async def health(request: Request):
    state: AppState | None = getattr(request.app.state, "fc", None)
    return {"status": "ok", "time": iso(utcnow()), "modules": len(state.cache.all_status()) if state else 0}


@router.get("/config/public", dependencies=[Depends(require_read)])
async def public_config(state: AppState = Depends(get_state)):
    return state.public_config()


@router.get("/status", dependencies=[Depends(require_read)])
async def status(state: AppState = Depends(get_state)):
    rows = []
    for row in state.cache.all_status():
        integration = state.integrations.get(row["module"])
        rows.append({**row, "mocked": integration.is_mocked() if integration else None, "setup_hint": integration.setup_hint() if integration else []})
    return {"integrations": rows, "mock_mode": state.settings.mock_mode}


@router.get("/settings", dependencies=[Depends(require_read)])
async def get_settings_view(state: AppState = Depends(get_state)):
    accounts = (state.firefly_data() or {}).get("accounts") or []
    return {
        "values": state.db.all_settings(),
        "card_accounts": state.card_accounts(),
        "accounts": [{"id": a["id"], "name": a["name"], "type": a["type"], "role": a.get("role")} for a in accounts],
        "catalog_last_verified": state.catalog.last_verified.isoformat(),
    }


class SettingsBody(BaseModel):
    values: dict[str, str | None]


ALLOWED_KEYS = {"privacy_blur", "weather_location", "kiosk_privacy_blur"}


@router.post("/settings", dependencies=[Depends(require_write)])
async def set_settings(body: SettingsBody, state: AppState = Depends(get_state)):
    for key, value in body.values.items():
        ok = key in ALLOWED_KEYS or key.startswith("card_account:")
        if not ok:
            continue
        if key.startswith("card_account:") and key.split(":", 1)[1] not in {c.id for c in state.config.cards}:
            continue
        if value is None or value == "":
            state.db.execute("DELETE FROM settings WHERE key = ?", (key,))
        else:
            state.db.set_setting(key, str(value))
    state.invalidate_benefits()
    return {"ok": True, "values": state.db.all_settings()}
