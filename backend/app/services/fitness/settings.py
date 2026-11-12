"""Dashboard side settings for the fitness analytics, stored as JSON in the settings table."""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import BaseModel, Field, model_validator

SETTINGS_KEY = "fitness_settings"
MAP_KEY_SETTING = "fitness_muscle_map"


class Zones(BaseModel):
    """Weekly fractional sets per muscle: under below_minimum_max is too little, under building_max is building,
    up to target_max is the target, past it is high."""

    below_minimum_max: Annotated[float, Field(ge=0, le=100)] = 4
    building_max: Annotated[float, Field(ge=0, le=100)] = 10
    target_max: Annotated[float, Field(ge=0, le=100)] = 20

    @model_validator(mode="after")
    def _ordered(self) -> Zones:
        if not self.below_minimum_max < self.building_max <= self.target_max:
            raise ValueError("zones must satisfy below_minimum_max < building_max <= target_max")
        return self


class FitnessSettings(BaseModel):
    alpha: Annotated[float, Field(gt=0, le=1)] = 0.1
    band_low_pct: Annotated[float, Field(ge=0, le=10)] = 1.0
    band_high_pct: Annotated[float, Field(ge=0, le=10)] = 1.5
    target_sessions: Annotated[int, Field(ge=1, le=14)] = 6
    zones: Zones = Zones()
    plateau_weeks: Annotated[int, Field(ge=2, le=26)] = 6
    flat_pct: Annotated[float, Field(ge=0, le=20)] = 1.0
    units: str = "lb"

    @model_validator(mode="after")
    def _band(self) -> FitnessSettings:
        if self.band_low_pct > self.band_high_pct:
            raise ValueError("band_low_pct must not exceed band_high_pct")
        return self


def load_settings(raw: str | None) -> FitnessSettings:
    """Stored JSON merged over the defaults; anything unreadable falls back to the defaults."""
    if not raw:
        return FitnessSettings()
    try:
        return FitnessSettings.model_validate(json.loads(raw))
    except Exception:
        return FitnessSettings()


def merge_settings(current: FitnessSettings, patch: dict[str, Any]) -> FitnessSettings:
    """A partial update validated as a whole, so a bad field never half applies."""
    data = current.model_dump()
    for key, value in patch.items():
        if key == "zones" and isinstance(value, dict):
            data["zones"] = {**data["zones"], **value}
        else:
            data[key] = value
    return FitnessSettings.model_validate(data)
