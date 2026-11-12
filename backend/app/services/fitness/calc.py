"""Pure fitness calculations. No I/O, no clock: every function takes its dates and settings as arguments.

Inputs are plain dicts shaped like Lock-In's export (weighIns, sessions, sets), already filtered of deleted rows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .muscle_map import MUSCLES, MuscleMap

DAYS_PER_MONTH = 30.4375
MIN_WEIGH_IN_DAYS = 14
RATE_WINDOW_DAYS = 28
E1RM_MAX_REPS = 10
MIN_SESSIONS_FOR_STALL = 4

TrendPoint = tuple[date, float | None, float]  # (day, raw weigh-in or None, trend)


# ---- weight -------------------------------------------------------------------------------------------------


def week_start(d: date) -> date:
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def trend_points(weigh_ins: list[dict[str, Any]], alpha: float, end: date) -> list[TrendPoint]:
    """Daily exponential moving average from the first weigh-in through `end`.

    trend = prev + alpha * (today - prev), seeded with the first weigh-in; a day without a weigh-in carries the
    trend forward unchanged. The last weigh-in of a day wins if there are several.
    """
    by_day: dict[date, float] = {}
    for w in weigh_ins:
        try:
            by_day[date.fromisoformat(str(w["date"])[:10])] = float(w["weightLb"])
        except (KeyError, TypeError, ValueError):
            continue
    if not by_day:
        return []
    day = min(by_day)
    trend = by_day[day]
    out: list[TrendPoint] = []
    while day <= end:
        raw = by_day.get(day)
        if raw is not None and out:
            trend = trend + alpha * (raw - trend)
        out.append((day, raw, trend))
        day += timedelta(days=1)
    return out


def _slope(xs: list[float], ys: list[float]) -> float:
    """Least squares slope; 0 when there is nothing to fit."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / den if den else 0.0


def rate_of_gain(points: list[TrendPoint], end: date, window_days: int = RATE_WINDOW_DAYS) -> dict[str, float] | None:
    """Regression slope of the trend over the last `window_days`, as lb per week and percent of bodyweight per month."""
    start = end - timedelta(days=window_days - 1)
    window = [(d, t) for d, _raw, t in points if start <= d <= end]
    if len(window) < 2:
        return None
    slope = _slope([float((d - start).days) for d, _ in window], [t for _, t in window])
    current = window[-1][1]
    return {
        "lb_per_week": slope * 7,
        "pct_per_month": (slope * DAYS_PER_MONTH / current * 100) if current else 0.0,
    }


def band_status(pct_per_month: float, low: float, high: float) -> str:
    if pct_per_month < low:
        return "below"
    return "in" if pct_per_month <= high else "above"


def weigh_in_days(weigh_ins: list[dict[str, Any]]) -> int:
    return len({str(w.get("date"))[:10] for w in weigh_ins if w.get("date") and w.get("weightLb") is not None})


def trend_at(points: list[TrendPoint], day: date) -> float | None:
    """The trend on `day`, or on the last day before it that exists."""
    best = None
    for d, _raw, t in points:
        if d > day:
            break
        best = t
    return best


def corridor(
    points: list[TrendPoint], end: date, low_pct: float, high_pct: float, back_days: int = RATE_WINDOW_DAYS, ahead_days: int = 30
) -> list[dict[str, Any]]:
    """The target band projected from the trend `back_days` ago: where the trend should be at the low and high rates."""
    anchor_day = end - timedelta(days=back_days)
    base = trend_at(points, anchor_day)
    if base is None:
        return []
    out = []
    for i in range(back_days + ahead_days + 1):
        d = anchor_day + timedelta(days=i)
        months = i / DAYS_PER_MONTH
        out.append({"date": d.isoformat(), "low": round(base * (1 + low_pct / 100) ** months, 2), "high": round(base * (1 + high_pct / 100) ** months, 2)})
    return out


# ---- sets and e1RM ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SetRow:
    day: date
    session_id: str
    exercise: str
    index: int
    weight: float
    reps: int


def dated_sets(sessions: list[dict[str, Any]], sets: list[dict[str, Any]], completed_only: bool = True) -> list[SetRow]:
    """Sets joined to their session's date, chronological. Sets of unknown or incomplete sessions are dropped."""
    day_of: dict[str, date] = {}
    for s in sessions:
        if completed_only and s.get("completedAt") is None:
            continue
        try:
            day_of[str(s["id"])] = date.fromisoformat(str(s["date"])[:10])
        except (KeyError, TypeError, ValueError):
            continue
    rows = []
    for st in sets:
        day = day_of.get(str(st.get("sessionId")))
        if day is None:
            continue
        try:
            rows.append(
                SetRow(
                    day, str(st["sessionId"]), str(st["exerciseKey"]), int(st.get("setIndex") or 0), float(st.get("weightLb") or 0), int(st.get("reps") or 0)
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda r: (r.day, r.session_id, r.exercise, r.index))
    return rows


def epley(weight: float, reps: int) -> float | None:
    """Estimated one rep max. Sets above 10 reps or without external load give no estimate."""
    if weight <= 0 or reps < 1 or reps > E1RM_MAX_REPS:
        return None
    return weight if reps == 1 else weight * (1 + reps / 30)


def session_e1rms(rows: list[SetRow]) -> dict[str, list[tuple[date, float]]]:
    """Per exercise, the best e1RM of each session, chronological."""
    best: dict[tuple[str, str, date], float] = {}
    for r in rows:
        e = epley(r.weight, r.reps)
        if e is None:
            continue
        key = (r.exercise, r.session_id, r.day)
        best[key] = max(best.get(key, 0.0), e)
    out: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for (exercise, _sid, day), e in sorted(best.items(), key=lambda kv: (kv[0][2], kv[0][1])):
        out[exercise].append((day, e))
    return dict(out)


# ---- volume -------------------------------------------------------------------------------------------------


def weekly_sets(rows: list[SetRow], muscle_map: MuscleMap, monday: date) -> dict[str, Any]:
    """Fractional sets per muscle for the week starting `monday`: 1.0 per primary, 0.5 per secondary muscle.

    Returns {"muscles": {muscle: total}, "exercises": {muscle: {exercise: sets}}, "unmapped": {exercise: count}}.
    """
    totals: dict[str, float] = dict.fromkeys(MUSCLES, 0.0)
    by_exercise: dict[str, dict[str, float]] = {m: defaultdict(float) for m in MUSCLES}
    unmapped: dict[str, int] = defaultdict(int)
    sunday = monday + timedelta(days=6)
    for r in rows:
        if not monday <= r.day <= sunday:
            continue
        entry = muscle_map.get(r.exercise)
        if entry is None:
            unmapped[r.exercise] += 1
            continue
        for m in entry.get("primary", []):
            totals[m] += 1.0
            by_exercise[m][r.exercise] += 1.0
        for m in entry.get("secondary", []):
            totals[m] += 0.5
            by_exercise[m][r.exercise] += 0.5
    return {"muscles": totals, "exercises": {m: dict(v) for m, v in by_exercise.items()}, "unmapped": dict(unmapped)}


def zone(sets: float, zones: Any) -> str:
    """under below_minimum_max: below_minimum; under building_max: building; up to target_max: target; else high."""
    if sets < zones.below_minimum_max:
        return "below_minimum"
    if sets < zones.building_max:
        return "building"
    return "target" if sets <= zones.target_max else "high"


def days_since_muscle(rows: list[SetRow], muscle_map: MuscleMap, today: date) -> dict[str, int | None]:
    """Days since each muscle last appeared in a logged set, as a primary or secondary muscle. None when never."""
    last: dict[str, date] = {}
    for r in rows:
        entry = muscle_map.get(r.exercise)
        if entry is None:
            continue
        for m in entry.get("primary", []) + entry.get("secondary", []):
            if m not in last or r.day > last[m]:
                last[m] = r.day
    return {m: ((today - last[m]).days if m in last else None) for m in MUSCLES}


# ---- PRs and stalls -----------------------------------------------------------------------------------------


def rep_prs(rows: list[SetRow]) -> dict[str, list[SetRow]]:
    """Per exercise, every set that was a rep PR when it happened: no earlier set had both weight >= and reps >=.

    Only loaded sets count (weight above zero), matching the e1RM rule for bodyweight work.
    """
    out: dict[str, list[SetRow]] = defaultdict(list)
    seen: dict[str, list[SetRow]] = defaultdict(list)
    for r in rows:
        if r.weight <= 0 or r.reps < 1:
            continue
        beaten = any(p.weight >= r.weight and p.reps >= r.reps for p in seen[r.exercise])
        if not beaten:
            out[r.exercise].append(r)
        seen[r.exercise].append(r)
    return dict(out)


def best_reps_per_weight(rows: list[SetRow], exercise: str) -> list[dict[str, Any]]:
    """The rep PR table for one exercise: the best reps achieved at each weight, heaviest first."""
    best: dict[float, tuple[int, date]] = {}
    for r in rows:
        if r.exercise != exercise or r.weight <= 0 or r.reps < 1:
            continue
        if r.weight not in best or r.reps > best[r.weight][0]:
            best[r.weight] = (r.reps, r.day)
    return [{"weight": w, "reps": reps, "date": d.isoformat()} for w, (reps, d) in sorted(best.items(), reverse=True)]


def e1rm_prs(points: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """Sessions whose e1RM beat the all-time best before them (the first session counts as the first best)."""
    out = []
    best = 0.0
    for d, e in points:
        if e > best:
            out.append((d, e))
            best = e
    return out


def stall(points: list[tuple[date, float]], today: date, weeks: int, flat_pct: float) -> dict[str, Any] | None:
    """Regression of e1RM over the plateau window. Needs at least 4 sessions in the window.

    Returns {"pct_change", "sessions", "points"} with pct_change from the fitted start to the fitted end, and
    "stalled" True when that change is under flat_pct (or negative).
    """
    start = today - timedelta(weeks=weeks)
    window = [(d, e) for d, e in points if start <= d <= today]
    if len(window) < MIN_SESSIONS_FOR_STALL:
        return None
    xs = [float((d - window[0][0]).days) for d, _ in window]
    ys = [e for _, e in window]
    slope = _slope(xs, ys)
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    fit_start = mean_y + slope * (xs[0] - mean_x)
    fit_end = mean_y + slope * (xs[-1] - mean_x)
    pct = (fit_end - fit_start) / fit_start * 100 if fit_start else 0.0
    return {"pct_change": pct, "sessions": len(window), "points": window, "stalled": pct < flat_pct}


# ---- consistency and bulk quality ---------------------------------------------------------------------------


def session_days(sessions: list[dict[str, Any]]) -> dict[date, int]:
    """Completed sessions per calendar day."""
    out: dict[date, int] = defaultdict(int)
    for s in sessions:
        if s.get("completedAt") is None:
            continue
        try:
            out[date.fromisoformat(str(s["date"])[:10])] += 1
        except (KeyError, TypeError, ValueError):
            continue
    return dict(out)


def strength_index(e1rms: dict[str, list[tuple[date, float]]], today: date, weeks: int = 8, min_sessions: int = 4) -> list[dict[str, Any]] | None:
    """Weekly strength index: each regularly trained exercise's best weekly e1RM normalized to 100 at its first
    week in the window, averaged across exercises. Missing weeks carry the last value forward."""
    first_monday = week_start(today) - timedelta(weeks=weeks - 1)
    mondays = [first_monday + timedelta(weeks=i) for i in range(weeks)]
    regular = {ex: pts for ex, pts in e1rms.items() if sum(1 for d, _ in pts if d >= first_monday) >= min_sessions}
    if not regular:
        return None
    per_week: list[list[float]] = [[] for _ in mondays]
    for pts in regular.values():
        weekly: list[float | None] = []
        for m in mondays:
            vals = [e for d, e in pts if m <= d <= m + timedelta(days=6)]
            weekly.append(max(vals) if vals else None)
        base = next((v for v in weekly if v is not None), None)
        if not base:
            continue
        last: float | None = None
        for i, v in enumerate(weekly):
            if v is not None:
                last = v
            if last is not None:
                per_week[i].append(last / base * 100)
    out = []
    carry = 100.0
    for m, vals in zip(mondays, per_week, strict=True):
        if vals:
            carry = sum(vals) / len(vals)
        out.append({"week_start": m.isoformat(), "strength_index": round(carry, 1)})
    return out


BULK_STATES = {
    "on_track": "on track",
    "gaining_without_strength": "gaining without getting stronger",
    "recomping": "recomping, consider eating more",
    "under_eating": "under-eating or under-recovering",
}


def bulk_state(weight_change_pct: float, strength_change_pct: float, weight_flat_pct: float = 1.0, strength_flat_pct: float = 2.0) -> str:
    """Four states from the direction of trend weight and strength index over the window."""
    weight_up = weight_change_pct >= weight_flat_pct
    strength_up = strength_change_pct >= strength_flat_pct
    if weight_up:
        return "on_track" if strength_up else "gaining_without_strength"
    return "recomping" if strength_up else "under_eating"
