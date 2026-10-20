"""Application settings read from the environment and the repository .env file."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/settings.py -> app -> backend -> repository root
ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"

# Load .env into os.environ so YAML config can reference arbitrary env var names
# (for example calendar feeds). Existing process environment always wins.
load_dotenv(ENV_FILE, override=False)


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore", case_sensitive=False)

    # Core
    app_port: int = 8000
    tz: str = "America/New_York"
    mock_mode: bool = True
    secret_key: str = "change-me-to-a-long-random-string"
    dashboard_password_hash: str = ""
    kiosk_token: str = ""
    session_days: int = 30

    # Per integration mock overrides (None means follow mock_mode)
    mock_weather: bool | None = None
    mock_calendar: bool | None = None
    mock_firefly: bool | None = None
    mock_plex: bool | None = None
    mock_vault: bool | None = None
    mock_docker: bool | None = None

    # Weather
    nws_user_agent: str = "(FrankensteinCentral, your-email@example.com)"

    # Calendar (feeds can reference any env var; these two are the defaults)
    gcal_ics_primary: str = ""
    gcal_ics_second: str = ""

    # Firefly III
    firefly_url: str = ""
    firefly_vanity_url: str = ""
    firefly_token: str = ""
    firefly_writeback_tags: bool = False
    firefly_importer_url: str = ""
    firefly_importer_secret: str = ""
    firefly_importer_dir: str = "/import"

    # Plex
    plex_url: str = ""
    plex_token: str = ""
    plex_public_url: str = "https://app.plex.tv/desktop"

    # Vaultwarden
    vaultwarden_url: str = ""
    vaultwarden_public_url: str = ""
    vaultwarden_backup_dir: str = ""

    # Docker
    docker_host: str = "tcp://socket-proxy:2375"
    docker_allow_restart: bool = False
    portainer_url: str = ""

    # Paths
    config_dir: Path = Field(default_factory=lambda: _first_existing(ROOT / "config", Path("config")))
    data_dir: Path = Field(default_factory=lambda: ROOT / "data")
    static_dir: Path = Field(default_factory=lambda: _first_existing(ROOT / "static", ROOT / "frontend" / "dist"))

    # ------------------------------------------------------------------
    def is_mocked(self, integration: str) -> bool:
        override = getattr(self, f"mock_{integration}", None)
        if override is None:
            return self.mock_mode
        return bool(override)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "frankenstein.db"

    def env_value(self, name: str) -> str:
        """Read an arbitrary env var (used for calendar feeds, link tiles, probes)."""
        return os.environ.get(name, "") or ""

    def secret_values(self) -> list[str]:
        """Every secret value that must never appear in logs."""
        values = [
            self.secret_key,
            self.dashboard_password_hash,
            self.kiosk_token,
            self.firefly_token,
            self.firefly_importer_secret,
            self.plex_token,
            self.gcal_ics_primary,
            self.gcal_ics_second,
        ]
        for key, value in os.environ.items():
            if key.startswith("GCAL_ICS_") and value:
                values.append(value)
        return [v for v in values if v and len(v) >= 8]


@lru_cache
def get_settings() -> Settings:
    return Settings()
