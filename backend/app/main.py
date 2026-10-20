"""FastAPI application: API routes plus static SPA hosting."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth as authlib
from .cache import Cache
from .config_loader import ConfigError, get_benefits_catalog, get_dashboard_config
from .db import Database
from .integrations.calendar_ics import CalendarIntegration
from .integrations.docker_proxy import DockerIntegration
from .integrations.firefly import FireflyIntegration
from .integrations.plex import PlexIntegration
from .integrations.probes import ProbesIntegration
from .integrations.vaultwarden import VaultwardenIntegration
from .integrations.weather import WeatherIntegration
from .logsetup import configure_logging, install_redaction
from .routes import auth as auth_routes
from .routes import benefits as benefits_routes
from .routes import finance as finance_routes
from .routes import health as health_routes
from .routes import modules as module_routes
from .settings import Settings, get_settings
from .state import AppState

log = logging.getLogger("frankenstein")


def build_state(settings: Settings | None = None, db_path: str | None = None, start_scheduler: bool = True) -> AppState:
    settings = settings or get_settings()
    try:
        config = get_dashboard_config()
        catalog = get_benefits_catalog()
    except ConfigError as exc:
        log.error("%s", exc)
        raise
    db = Database(db_path or settings.db_path)
    cache = Cache(db)
    state = AppState(settings, config, catalog, db, cache)
    integrations = [
        WeatherIntegration(settings, config),
        CalendarIntegration(settings, config),
        FireflyIntegration(settings, config),
        PlexIntegration(settings, config, client_id_provider=state.plex_client_id),
        VaultwardenIntegration(settings, config),
        DockerIntegration(settings, config),
        ProbesIntegration(settings, config),
    ]
    for integration in integrations:
        state.integrations[integration.name] = integration
        state.scheduler.register(integration)
    state.scheduler.on_success("firefly", state.invalidate_benefits)
    state.scheduler.on_success("firefly", state.snapshot_benefits)
    return state


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    install_redaction(settings.secret_values())
    try:
        state = build_state(settings)
    except ConfigError:
        sys.exit(1)
    app.state.fc = state
    if not authlib.password_configured(settings):
        log.warning("DASHBOARD_PASSWORD_HASH is empty: any password is accepted. Generate one with python -m app.hash_password")
    if settings.secret_key.startswith("change-me"):
        log.warning("SECRET_KEY is the default value. Set a long random string in .env")
    log.info(
        "FrankensteinCentral starting (mock_mode=%s, tz=%s, integrations=%s)",
        settings.mock_mode,
        state.config.timezone,
        ",".join(f"{n}:{'mock' if i.is_mocked() else ('live' if i.is_configured() else 'off')}" for n, i in state.integrations.items()),
    )
    await state.scheduler.start()
    try:
        yield
    finally:
        await state.scheduler.stop()
        state.db.close()


app = FastAPI(title="FrankensteinCentral", docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(health_routes.router)
app.include_router(auth_routes.router)
app.include_router(module_routes.router)
app.include_router(finance_routes.router)
app.include_router(benefits_routes.router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse({"detail": f"Internal error: {exc.__class__.__name__}"}, status_code=500)


def mount_static(application: FastAPI) -> None:
    settings = get_settings()
    static_dir: Path = settings.static_dir
    index = static_dir / "index.html"
    if (static_dir / "assets").exists():
        application.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str, request: Request):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = static_dir / full_path
        if full_path and candidate.is_file() and candidate.resolve().is_relative_to(static_dir.resolve()):
            return FileResponse(candidate)
        if not index.exists():
            return JSONResponse({"detail": "Frontend not built. Run npm run build in frontend/."}, status_code=503)
        if full_path.rstrip("/") == "kiosk" and "token" in request.query_params:
            # /kiosk?token=... sets the read-only kiosk cookie and drops the token from the URL
            token = request.query_params.get("token")
            if authlib.kiosk_token_valid(token):
                response = RedirectResponse("/kiosk", status_code=303)
                authlib.set_kiosk_cookie(request, response)
                return response
        return FileResponse(index)


mount_static(app)
