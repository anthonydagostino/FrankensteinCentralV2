"""Envelope routes for the simple modules: weather, calendar, plex, vault, containers, probes, attention."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from ..auth import require_read, require_write
from ..deps import get_state
from ..integrations.base import make_client
from ..integrations.docker_proxy import restart_container
from ..state import AppState

router = APIRouter(prefix="/api", tags=["modules"], dependencies=[Depends(require_read)])


@router.get("/weather")
async def weather(location: str | None = None, state: AppState = Depends(get_state)):
    env = state.cache.envelope("weather")
    data = env.get("data") or {}
    locs = data.get("locations") or {}
    chosen = location or state.db.get_setting("weather_location") or data.get("default")
    picked = locs.get(chosen) if chosen else None
    if picked is None and locs:
        picked = locs.get(data.get("default")) or next(iter(locs.values()))
    env["data"] = {**(picked or {}), "available": list(locs.keys()), "units": data.get("units")} if picked else None
    return env


@router.get("/calendar")
async def calendar(days: int = Query(7, ge=1, le=31), state: AppState = Depends(get_state)):
    env = state.cache.envelope("calendar")
    data = env.get("data")
    if data:
        env["data"] = {**data, "days": (data.get("days") or [])[:days]}
    return env


@router.get("/plex")
async def plex(state: AppState = Depends(get_state)):
    return state.cache.envelope("plex")


@router.get("/plex/image")
async def plex_image(path: str, w: int = Query(300, ge=16, le=2000), h: int = Query(450, ge=16, le=2000), state: AppState = Depends(get_state)):
    if not path.startswith("/library/") or ".." in path:
        raise HTTPException(status_code=400, detail="path must start with /library/")
    integration = state.integrations.get("plex")
    if integration is None or integration.is_mocked() or not integration.is_configured():
        svg = _placeholder_svg(path, w, h)
        return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})
    url = f"{state.settings.plex_url.rstrip('/')}/photo/:/transcode"
    params = {"width": w, "height": h, "minSize": 1, "upscale": 1, "url": path}
    async with make_client(headers=integration.headers()) as client:
        resp = await client.get(url, params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Plex image unavailable")
    return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"), headers={"Cache-Control": "public, max-age=86400"})


def _placeholder_svg(path: str, w: int, h: int) -> str:
    seed = sum(ord(c) for c in path)
    hue = seed % 360
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl({hue},45%,28%)"/><stop offset="1" stop-color="hsl({(hue + 50) % 360},40%,12%)"/></linearGradient></defs>'
        f'<rect width="{w}" height="{h}" fill="url(#g)"/>'
        f'<circle cx="{w * 0.5}" cy="{h * 0.42}" r="{min(w, h) * 0.16}" fill="rgba(255,255,255,0.12)"/>'
        f"</svg>"
    )


@router.get("/vault")
async def vault(state: AppState = Depends(get_state)):
    return state.cache.envelope("vault")


@router.get("/containers")
async def containers(state: AppState = Depends(get_state)):
    return state.cache.envelope("docker")


@router.post("/containers/{cid}/restart", dependencies=[Depends(require_write)])
async def restart(cid: str, state: AppState = Depends(get_state)):
    if not state.settings.docker_allow_restart:
        raise HTTPException(status_code=403, detail="Container restarts are disabled (DOCKER_ALLOW_RESTART=false)")
    if not cid.isalnum() or len(cid) > 64:
        raise HTTPException(status_code=400, detail="Invalid container id")
    integration = state.integrations.get("docker")
    if integration is not None and integration.is_mocked():
        return {"ok": True, "mocked": True}
    status = await restart_container(state.settings, cid)
    if status >= 400:
        raise HTTPException(status_code=502, detail=f"Docker returned HTTP {status}. Check POST=1 and ALLOW_RESTARTS=1 on the socket proxy.")
    state.scheduler.trigger("docker")
    return {"ok": True}


@router.get("/lockin")
async def lockin(state: AppState = Depends(get_state)):
    return state.cache.envelope("lockin")


@router.get("/probes")
async def probes(state: AppState = Depends(get_state)):
    return state.cache.envelope("probes")


@router.get("/attention")
async def attention(request: Request, location: str | None = None, state: AppState = Depends(get_state)):
    items = state.attention(location)
    return {"module": "attention", "status": "ok", "configured": True, "fetched_at": None, "stale": False, "error": None, "data": {"items": items}}
