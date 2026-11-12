"""Exercise to muscle map. Seeded for every exercise in Lock-In's program; edits are stored dashboard side."""

from __future__ import annotations

import json
from typing import Any

MUSCLES = ["chest", "back", "shoulders", "biceps", "triceps", "quads", "hamstrings", "glutes", "calves", "abs"]

# exercise key -> (display name, primary muscles, secondary muscles). Primary counts 1.0 set, secondary 0.5.
SEED: dict[str, tuple[str, list[str], list[str]]] = {
    "incline-db-press": ("Incline dumbbell press", ["chest"], ["shoulders", "triceps"]),
    "flat-bench": ("Flat bench press", ["chest"], ["triceps", "shoulders"]),
    "cable-fly": ("Cable fly", ["chest"], []),
    "seated-db-shoulder-press": ("Seated dumbbell shoulder press", ["shoulders"], ["triceps"]),
    "cable-lateral-raise": ("Cable lateral raise", ["shoulders"], []),
    "rope-pushdown": ("Rope pushdown", ["triceps"], []),
    "overhead-cable-triceps": ("Overhead cable triceps extension", ["triceps"], []),
    "pullup-or-pulldown": ("Pull-up or lat pulldown", ["back"], ["biceps"]),
    "chest-supported-row": ("Chest-supported row", ["back"], ["biceps"]),
    "single-arm-cable-lat-row": ("Single-arm cable lat row", ["back"], ["biceps"]),
    "reverse-pec-deck": ("Reverse pec deck", ["shoulders"], ["back"]),
    "ez-bar-curl": ("EZ-bar curl", ["biceps"], []),
    "hammer-curl": ("Hammer curl", ["biceps"], []),
    "squat-or-hack": ("Squat or hack squat", ["quads"], ["glutes"]),
    "romanian-deadlift": ("Romanian deadlift", ["hamstrings"], ["glutes", "back"]),
    "leg-extension": ("Leg extension", ["quads"], []),
    "seated-leg-curl": ("Seated leg curl", ["hamstrings"], []),
    "standing-calf-raise": ("Standing calf raise", ["calves"], []),
    "cable-crunch": ("Cable crunch", ["abs"], []),
    "overhead-press": ("Overhead press", ["shoulders"], ["triceps"]),
    "incline-machine-press": ("Incline machine press", ["chest"], ["shoulders", "triceps"]),
    "dips": ("Dips", ["chest"], ["triceps", "shoulders"]),
    "pec-deck": ("Pec deck", ["chest"], []),
    "ez-skull-crusher": ("EZ-bar skull crusher", ["triceps"], []),
    "single-arm-pushdown": ("Single-arm pushdown", ["triceps"], []),
    "barbell-or-tbar-row": ("Barbell or T-bar row", ["back"], ["biceps"]),
    "neutral-grip-pulldown": ("Neutral-grip pulldown", ["back"], ["biceps"]),
    "seated-cable-row": ("Seated cable row", ["back"], ["biceps"]),
    "face-pull": ("Face pull", ["shoulders"], ["back"]),
    "incline-db-curl": ("Incline dumbbell curl", ["biceps"], []),
    "preacher-or-cable-curl": ("Preacher or cable curl", ["biceps"], []),
    "leg-press": ("Leg press", ["quads"], ["glutes"]),
    "bulgarian-split-squat": ("Bulgarian split squat", ["quads"], ["glutes", "hamstrings"]),
    "lying-leg-curl": ("Lying leg curl", ["hamstrings"], []),
    "hip-thrust-or-back-ext": ("Hip thrust or back extension", ["glutes"], ["hamstrings"]),
    "seated-calf-raise": ("Seated calf raise", ["calves"], []),
    "hanging-leg-raise": ("Hanging leg raise", ["abs"], []),
}

MuscleMap = dict[str, dict[str, Any]]


def seed_map() -> MuscleMap:
    return {key: {"name": name, "primary": list(primary), "secondary": list(secondary)} for key, (name, primary, secondary) in SEED.items()}


def load_map(raw: str | None) -> MuscleMap:
    """The seed with the stored overrides merged on top (an override replaces that exercise's whole entry)."""
    out = seed_map()
    if raw:
        try:
            overrides = json.loads(raw)
        except ValueError:
            overrides = {}
        if isinstance(overrides, dict):
            for key, entry in overrides.items():
                try:
                    out[key] = validate_entry(key, entry)
                except ValueError:
                    continue
    return out


def validate_entry(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    """One map entry: primary and secondary are muscle names and never overlap; name defaults to the key."""
    if not key or not isinstance(entry, dict):
        raise ValueError("bad entry")
    primary = [str(m) for m in entry.get("primary") or []]
    secondary = [str(m) for m in entry.get("secondary") or []]
    for m in primary + secondary:
        if m not in MUSCLES:
            raise ValueError(f"unknown muscle {m!r}")
    if set(primary) & set(secondary):
        raise ValueError("a muscle cannot be both primary and secondary")
    if not primary and not secondary:
        raise ValueError("at least one muscle is required")
    name = str(entry.get("name") or key).strip()[:80] or key
    return {"name": name, "primary": primary, "secondary": secondary}
