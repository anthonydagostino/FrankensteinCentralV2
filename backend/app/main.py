"""FastAPI application: API routes plus static SPA hosting."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config_loader import get_benefits_catalog, get_dashboard_config
from .settings import get_settings

log = logging.getLogger("frankenstein")

app = FastAPI(title="FrankensteinCentral", docs_url=None, redoc_url=None)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


def mount_static(application: FastAPI) -> None:
    settings = get_settings()
    static_dir: Path = settings.static_dir
    index = static_dir / "index.html"
    if (static_dir / "assets").exists():
        application.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": "Frontend not built. Run npm run build in frontend/."}, status_code=503)


@app.on_event("startup")
async def _startup() -> None:
    settings = get_settings()
    dash = get_dashboard_config()
    catalog = get_benefits_catalog()
    log.info("config loaded: %d locations, %d benefits, mock_mode=%s", len(dash.weather.locations), len(catalog.benefits), settings.mock_mode)


mount_static(app)
