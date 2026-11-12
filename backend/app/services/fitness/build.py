"""Assemble the /api/fitness payload from the Lock-In export, the settings, and the muscle map."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import calc
from .muscle_map import MUSCLES, MuscleMap
from .settings import FitnessSettings

SERIES_DAYS = 120
HEATMAP_WEEKS = 12
VOLUME_WEEKS = 8
BULK_WEEKS = 8
RECENT_PRS = 25


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def build_fitness(export: dict[str, Any], today: date, settings: FitnessSettings, muscle_map: MuscleMap) -> dict[str, Any]:
    weigh_ins = [w for w in export.get("weighIns") or [] if not w.get("deleted")]
    sessions = [s for s in export.get("sessions") or [] if not s.get("deleted")]
    sets = [s for s in export.get("sets") or [] if not s.get("deleted")]
    rows = calc.dated_sets(sessions, sets)
    e1rms = calc.session_e1rms(rows)
    monday = calc.week_start(today)
    names = {k: v["name"] for k, v in muscle_map.items()}
    return {
        "as_of": today.isoformat(),
        "units": settings.units,
        "settings": settings.model_dump(),
        "weight": _weight(weigh_ins, today, settings),
        "consistency": _consistency(sessions, rows, muscle_map, today, settings),
        "volume": _volume(rows, muscle_map, monday, settings),
        "strength": _strength(rows, e1rms, names, monday),
        "stalled": _stalled(e1rms, names, today, settings),
        "bulk_quality": _bulk_quality(weigh_ins, e1rms, today, settings),
        "muscle_map": muscle_map,
    }


def _weight(weigh_ins: list[dict[str, Any]], today: date, s: FitnessSettings) -> dict[str, Any]:
    points = calc.trend_points(weigh_ins, s.alpha, today)
    days = calc.weigh_in_days(weigh_ins)
    collecting = days < calc.MIN_WEIGH_IN_DAYS
    rate = None if collecting else calc.rate_of_gain(points, today)
    current = points[-1][2] if points else None
    out: dict[str, Any] = {
        "status": "collecting" if collecting else "ok",
        "days_of_data": days,
        "trend": {"date": points[-1][0].isoformat(), "lb": _r(current)} if points else None,
        "rate": None,
        "change_30d_lb": None,
        "change_90d_lb": None,
        "series": [{"date": d.isoformat(), "raw": raw, "trend": _r(t, 2)} for d, raw, t in points[-SERIES_DAYS:]],
        "corridor": [] if collecting else calc.corridor(points, today, s.band_low_pct, s.band_high_pct),
    }
    if rate:
        out["rate"] = {
            "lb_per_week": _r(rate["lb_per_week"], 2),
            "pct_per_month": _r(rate["pct_per_month"], 2),
            "band": calc.band_status(rate["pct_per_month"], s.band_low_pct, s.band_high_pct),
        }
    if current is not None:
        for key, back in (("change_30d_lb", 30), ("change_90d_lb", 90)):
            then = calc.trend_at(points, today - timedelta(days=back))
            if then is not None and points[0][0] <= today - timedelta(days=back):
                out[key] = _r(current - then)
    return out


def _consistency(sessions: list[dict[str, Any]], rows: list[calc.SetRow], muscle_map: MuscleMap, today: date, s: FitnessSettings) -> dict[str, Any]:
    per_day = calc.session_days(sessions)
    monday = calc.week_start(today)
    first = monday - timedelta(weeks=HEATMAP_WEEKS - 1)
    weeks = []
    for i in range(HEATMAP_WEEKS):
        m = first + timedelta(weeks=i)
        weeks.append({"week_start": m.isoformat(), "sessions": sum(per_day.get(m + timedelta(days=d), 0) for d in range(7))})
    heatmap = [{"date": (first + timedelta(days=i)).isoformat(), "sessions": per_day.get(first + timedelta(days=i), 0)} for i in range(HEATMAP_WEEKS * 7)]
    since = calc.days_since_muscle(rows, muscle_map, today)
    return {
        "week_start": monday.isoformat(),
        "this_week": weeks[-1]["sessions"],
        "target": s.target_sessions,
        "weeks": weeks,
        "heatmap": heatmap,
        "days_since_muscle": [{"muscle": m, "days": since[m]} for m in MUSCLES],
    }


def _volume(rows: list[calc.SetRow], muscle_map: MuscleMap, monday: date, s: FitnessSettings) -> dict[str, Any]:
    this_week = calc.weekly_sets(rows, muscle_map, monday)
    muscles = []
    for m in MUSCLES:
        total = this_week["muscles"][m]
        contributors = sorted(this_week["exercises"][m].items(), key=lambda kv: -kv[1])
        muscles.append(
            {
                "muscle": m,
                "sets": _r(total),
                "zone": calc.zone(total, s.zones),
                "exercises": [{"exercise_key": k, "name": muscle_map[k]["name"], "sets": _r(v)} for k, v in contributors],
            }
        )
    weeks = []
    for i in range(VOLUME_WEEKS - 1, -1, -1):
        start = monday - timedelta(weeks=i)
        weeks.append({"week_start": start.isoformat(), "sets": {k: _r(v) for k, v in calc.weekly_sets(rows, muscle_map, start)["muscles"].items()}})
    # unmapped exercises over the whole history, so a new exercise shows up the week it is first logged
    unmapped: dict[str, int] = {}
    for r in rows:
        if r.exercise not in muscle_map:
            unmapped[r.exercise] = unmapped.get(r.exercise, 0) + 1
    return {
        "week_start": monday.isoformat(),
        "muscles": muscles,
        "weeks": weeks,
        "unmapped": [{"exercise_key": k, "sets": v} for k, v in sorted(unmapped.items())],
        "zones": s.zones.model_dump(),
    }


def _strength(rows: list[calc.SetRow], e1rms: dict[str, list[tuple[date, float]]], names: dict[str, str], monday: date) -> dict[str, Any]:
    prs_by_exercise = calc.rep_prs(rows)
    recent: list[dict[str, Any]] = []
    exercises = []
    best_set_by_day: dict[tuple[str, date], calc.SetRow] = {}
    for r in rows:
        key = (r.exercise, r.day)
        e = calc.epley(r.weight, r.reps) or 0.0
        if key not in best_set_by_day or e > (calc.epley(best_set_by_day[key].weight, best_set_by_day[key].reps) or 0.0):
            best_set_by_day[key] = r
    for exercise, points in sorted(e1rms.items(), key=lambda kv: -len(kv[1])):
        pr_days = {d for d, _ in calc.e1rm_prs(points)}
        exercises.append(
            {
                "exercise_key": exercise,
                "name": names.get(exercise, exercise),
                "best_e1rm": _r(max(e for _, e in points)),
                "sessions": len(points),
                "points": [{"date": d.isoformat(), "e1rm": _r(e), "pr": d in pr_days} for d, e in points],
                "rep_prs": calc.best_reps_per_weight(rows, exercise),
            }
        )
        for d, e in calc.e1rm_prs(points)[1:]:  # the very first session is a baseline, not a PR
            top = best_set_by_day.get((exercise, d))
            recent.append(
                {
                    "date": d.isoformat(),
                    "exercise_key": exercise,
                    "name": names.get(exercise, exercise),
                    "kind": "e1rm",
                    "weight": top.weight if top else None,
                    "reps": top.reps if top else None,
                    "e1rm": _r(e),
                }
            )
    first_day: dict[str, date] = {ex: pts[0][0] for ex, pts in e1rms.items()}
    for exercise, prs in prs_by_exercise.items():
        for r in prs:
            if first_day.get(exercise) == r.day:
                continue  # everything in the first session is trivially a PR
            recent.append(
                {
                    "date": r.day.isoformat(),
                    "exercise_key": exercise,
                    "name": names.get(exercise, exercise),
                    "kind": "rep",
                    "weight": r.weight,
                    "reps": r.reps,
                    "e1rm": _r(calc.epley(r.weight, r.reps)),
                }
            )
    recent.sort(key=lambda p: (p["date"], p["kind"]), reverse=True)
    week_end = (monday + timedelta(days=6)).isoformat()
    prs_this_week = sum(1 for p in recent if monday.isoformat() <= p["date"] <= week_end)
    return {"prs_this_week": prs_this_week, "exercises": exercises, "recent_prs": recent[:RECENT_PRS]}


def _stalled(e1rms: dict[str, list[tuple[date, float]]], names: dict[str, str], today: date, s: FitnessSettings) -> dict[str, Any]:
    items = []
    for exercise, points in e1rms.items():
        result = calc.stall(points, today, s.plateau_weeks, s.flat_pct)
        if result and result["stalled"]:
            items.append(
                {
                    "exercise_key": exercise,
                    "name": names.get(exercise, exercise),
                    "pct_change": _r(result["pct_change"]),
                    "sessions": result["sessions"],
                    "sparkline": [{"date": d.isoformat(), "e1rm": _r(e)} for d, e in result["points"]],
                }
            )
    items.sort(key=lambda i: i["pct_change"])
    return {"count": len(items), "window_weeks": s.plateau_weeks, "items": items}


def _bulk_quality(weigh_ins: list[dict[str, Any]], e1rms: dict[str, list[tuple[date, float]]], today: date, s: FitnessSettings) -> dict[str, Any] | None:
    if calc.weigh_in_days(weigh_ins) < calc.MIN_WEIGH_IN_DAYS:
        return None
    index = calc.strength_index(e1rms, today, BULK_WEEKS)
    if not index:
        return None
    points = calc.trend_points(weigh_ins, s.alpha, today)
    weeks = []
    for entry in index:
        m = date.fromisoformat(entry["week_start"])
        weeks.append({**entry, "trend_lb": _r(calc.trend_at(points, min(m + timedelta(days=6), today)))})
    first = next((w["trend_lb"] for w in weeks if w["trend_lb"] is not None), None)
    last = next((w["trend_lb"] for w in reversed(weeks) if w["trend_lb"] is not None), None)
    if first is None or last is None or not first:
        return None
    weight_change = (last - first) / first * 100
    strength_change = weeks[-1]["strength_index"] - 100
    state = calc.bulk_state(weight_change, strength_change)
    return {
        "state": state,
        "label": calc.BULK_STATES[state],
        "weight_change_pct": _r(weight_change),
        "strength_change_pct": _r(strength_change),
        "weeks": weeks,
    }
