"""Fitness analytics: the derived view, its settings, and the exercise to muscle map."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from ..auth import require_read, require_write
from ..deps import get_state
from ..services.fitness.muscle_map import MUSCLES, validate_entry
from ..services.fitness.settings import merge_settings
from ..state import AppState

router = APIRouter(prefix="/api/fitness", tags=["fitness"])


class MuscleEntryBody(BaseModel):
    exercise_key: str
    name: str | None = None
    primary: list[str] = []
    secondary: list[str] = []


def _derived_from_lockin(state: AppState) -> dict[str, Any]:
    """The lockin envelope with the fitness payload as data: same status, freshness and errors as its source."""
    env = state.cache.envelope("lockin")
    env["module"] = "fitness"
    if env["data"] is not None:
        try:
            env["data"] = state.fitness()
        except Exception as exc:
            env["status"] = "error"
            env["error"] = f"Could not compute fitness: {exc.__class__.__name__}"
            env["data"] = None
    return env


@router.get("", dependencies=[Depends(require_read)])
async def fitness(state: AppState = Depends(get_state)) -> dict[str, Any]:
    return _derived_from_lockin(state)


@router.get("/settings", dependencies=[Depends(require_read)])
async def get_settings(state: AppState = Depends(get_state)) -> dict[str, Any]:
    return state.fitness_settings().model_dump()


@router.put("/settings", dependencies=[Depends(require_write)])
async def put_settings(body: dict[str, Any], state: AppState = Depends(get_state)) -> dict[str, Any]:
    try:
        merged = merge_settings(state.fitness_settings(), body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()[0]["msg"]) from exc
    state.save_fitness_settings(merged)
    return merged.model_dump()


def _map_payload(state: AppState) -> dict[str, Any]:
    muscle_map = state.muscle_map()
    export = (state.cache.data("lockin") or {}).get("_export") or {}
    logged = {str(s.get("exerciseKey")) for s in export.get("sets") or [] if not s.get("deleted")}
    return {"map": muscle_map, "muscles": MUSCLES, "unmapped": sorted(k for k in logged if k not in muscle_map)}


@router.get("/muscle-map", dependencies=[Depends(require_read)])
async def get_map(state: AppState = Depends(get_state)) -> dict[str, Any]:
    return _map_payload(state)


@router.put("/muscle-map", dependencies=[Depends(require_write)])
async def put_map(body: MuscleEntryBody, state: AppState = Depends(get_state)) -> dict[str, Any]:
    key = body.exercise_key.strip()
    try:
        entry = validate_entry(key, {"name": body.name, "primary": body.primary, "secondary": body.secondary})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state.save_muscle_entry(key, entry)
    return _map_payload(state)
