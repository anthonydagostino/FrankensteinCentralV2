"""Loads and validates config/dashboard.yaml and config/benefits.yaml."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ConfigError(RuntimeError):
    """Raised when a YAML config file is missing or invalid."""


# --------------------------------------------------------------------------
# dashboard.yaml
# --------------------------------------------------------------------------
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Location(StrictModel):
    name: str
    lat: float
    lon: float
    default: bool = False


class WeatherConfig(StrictModel):
    locations: list[Location] = Field(min_length=1)
    units: Literal["imperial", "metric"] = "imperial"

    @model_validator(mode="after")
    def _one_default(self) -> "WeatherConfig":
        if not any(loc.default for loc in self.locations):
            self.locations[0].default = True
        return self

    @property
    def default_location(self) -> Location:
        return next(loc for loc in self.locations if loc.default)


class Feed(StrictModel):
    name: str
    env: str
    color: str = "#4ade80"


class CalendarConfig(StrictModel):
    lookahead_days: int = 30
    feeds: list[Feed] = []


class FinanceConfig(StrictModel):
    currency: str = "USD"
    hide_amounts_by_default: bool = False
    kiosk_hide_amounts: bool = True
    stale_after_hours: int = 48
    net_worth_include_types: list[str] = ["asset", "liabilities"]


class CardConfig(StrictModel):
    id: str
    label: str
    firefly_account_match: str = ""
    firefly_account_id: int | None = None
    annual_fee: Decimal = Decimal("0")


class LinkTile(StrictModel):
    name: str
    env_url: str
    icon: str = "link"


class Probe(StrictModel):
    name: str
    url_env: str
    path: str = "/"
    auth: str | None = None
    expect: int = 200


class UiConfig(StrictModel):
    theme: str = "dark"
    accent: str = "#4ade80"
    kiosk_rotate_seconds: int = 0


class DashboardConfig(StrictModel):
    owner_name: str = "Anthony"
    timezone: str = "America/New_York"
    weather: WeatherConfig
    calendar: CalendarConfig = CalendarConfig()
    finance: FinanceConfig = FinanceConfig()
    cards: list[CardConfig] = []
    links: list[LinkTile] = []
    probes: list[Probe] = []
    ui: UiConfig = UiConfig()


# --------------------------------------------------------------------------
# benefits.yaml
# --------------------------------------------------------------------------
Period = Literal["monthly", "quarterly", "semiannual", "annual", "multi_year"]
Tracking = Literal["matched", "credits_only", "manual"]


class BenefitConfig(StrictModel):
    id: str
    card: str
    name: str
    cap: Decimal
    period: Period
    period_caps: dict[str, Decimal] = {}
    period_years: float = 4.0  # multi_year only
    tracking: Tracking = "matched"
    enrollment_required: bool = True
    active_from: date | None = None
    active_until: date | None = None
    purchase_patterns: list[str] = []
    purchase_exclude_patterns: list[str] = []
    credit_patterns: list[str] = []
    notes: str = ""

    @field_validator("period_caps", mode="before")
    @classmethod
    def _string_keys(cls, value):
        if isinstance(value, dict):
            return {str(k): v for k, v in value.items()}
        return value


class BenefitsCatalog(StrictModel):
    last_verified: date
    benefits: list[BenefitConfig]

    @model_validator(mode="after")
    def _unique_ids(self) -> "BenefitsCatalog":
        seen: set[str] = set()
        for b in self.benefits:
            if b.id in seen:
                raise ValueError(f"duplicate benefit id: {b.id}")
            seen.add(b.id)
        return self


# --------------------------------------------------------------------------
def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"Invalid config file {path}:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"  key '{loc}': {err['msg']}")
    return "\n".join(lines)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Could not parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def load_dashboard_config(path: Path) -> DashboardConfig:
    data = _load_yaml(path)
    try:
        return DashboardConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(path, exc)) from exc


def load_benefits_catalog(path: Path) -> BenefitsCatalog:
    data = _load_yaml(path)
    try:
        return BenefitsCatalog.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(path, exc)) from exc


@lru_cache
def get_dashboard_config() -> DashboardConfig:
    from .settings import get_settings

    return load_dashboard_config(get_settings().config_dir / "dashboard.yaml")


@lru_cache
def get_benefits_catalog() -> BenefitsCatalog:
    from .settings import get_settings

    return load_benefits_catalog(get_settings().config_dir / "benefits.yaml")
