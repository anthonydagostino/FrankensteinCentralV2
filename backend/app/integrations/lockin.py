"""Lock-In: Anthony's offline-first training tracker (Node + SQLite on the homelab).

Read only. Uses GET /api/health (version), GET /api/summary (the dashboard feed), and
GET /api/export (weigh-ins and sessions) to draw the week squares and the weight trend.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from ..util import iso, local_now, today_local, utcnow
from .base import BaseIntegration, Degraded, describe_error, load_fixture, make_client, request

log = logging.getLogger("frankenstein.lockin")

FIXTURE_ANCHOR = date(2026, 10, 25)
WEIGHT_SERIES_DAYS = 60
STREAK_MIN_SESSIONS = 5
GOAL_DATE = date(2027, 6, 1)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def build_training(summary: dict, export: dict | None, today: date, now: datetime, public_url: str | None, version: str | None) -> dict:
    """Turn Lock-In's summary (plus the optional export) into the dashboard shape."""
    weight = summary.get("weight") or {}
    latest = weight.get("latest") or None
    target = weight.get("targetWeeklyChangeLb")
    change = weight.get("weeklyChangeLb")
    on_track = None
    if change is not None and target is not None:
        # within half a pound per week of the target counts as on track
        on_track = abs(float(change) - float(target)) <= 0.5

    sessions_this_week = int(summary.get("sessionsThisWeek") or 0)
    planned = int(summary.get("sessionsPlannedPerWeek") or 6)
    days_left_in_week = 7 - today.weekday()  # including today
    needed = max(0, STREAK_MIN_SESSIONS - sessions_this_week)
    if needed == 0:
        streak_risk = "safe"
    elif needed > days_left_in_week:
        streak_risk = "lost"
    elif needed == days_left_in_week:
        streak_risk = "at_risk"
    else:
        streak_risk = "ok"

    week: list[dict] | None = None
    weight_series: list[dict] | None = None
    trained_today = False
    if export:
        done_dates = {s["date"] for s in export.get("sessions") or [] if s.get("completedAt") is not None and not s.get("deleted")}
        ws = week_start(today)
        week = []
        for i in range(7):
            d = ws + timedelta(days=i)
            week.append({"date": d.isoformat(), "label": "MTWTFSS"[i], "done": d.isoformat() in done_dates, "today": d == today, "future": d > today})
        trained_today = today.isoformat() in done_dates
        cutoff = (today - timedelta(days=WEIGHT_SERIES_DAYS)).isoformat()
        series = sorted(((w["date"], float(w["weightLb"])) for w in export.get("weighIns") or [] if not w.get("deleted") and w["date"] > cutoff), key=lambda x: x[0])
        weight_series = [{"date": d, "weight": round(v, 1)} for d, v in series]
    elif summary.get("lastSession"):
        trained_today = summary["lastSession"].get("date") == today.isoformat()

    weighed_today = bool(latest and latest.get("date") == today.isoformat())
    phase = summary.get("phase") or {}
    last = summary.get("lastSession") or None
    nxt = summary.get("nextSession") or {}
    goal_days = summary.get("daysUntilGoal")
    if goal_days is None:
        goal_days = max(0, (GOAL_DATE - today).days)
    return {
        "version": version,
        "today": today.isoformat(),
        "phase": {"key": phase.get("key"), "name": phase.get("name"), "week": phase.get("week"), "deload": bool(phase.get("deload"))},
        "days_until_goal": int(goal_days),
        "goal_date": GOAL_DATE.isoformat(),
        "sessions_this_week": sessions_this_week,
        "sessions_planned": planned,
        "streak_weeks": int(summary.get("trainingStreakWeeks") or 0),
        "streak_min_sessions": STREAK_MIN_SESSIONS,
        "streak_risk": streak_risk,
        "sessions_needed_for_streak": needed,
        "days_left_in_week": days_left_in_week,
        "last_session": {"date": last.get("date"), "template_key": last.get("templateKey"), "name": last.get("templateName")} if last else None,
        "next_session": {"template_key": nxt.get("templateKey"), "name": nxt.get("templateName")} if nxt else None,
        "trained_today": trained_today,
        "weighed_today": weighed_today,
        "weight": {
            "latest": {"date": latest.get("date"), "lb": latest.get("weightLb")} if latest else None,
            "avg7": weight.get("avg7"),
            "avg7_prev": weight.get("avg7Prev"),
            "weekly_change": change,
            "target_weekly_change": target,
            "on_track": on_track,
        },
        "week": week,
        "weight_series": weight_series,
        "public_url": public_url or None,
        "generated_at": iso(now),
    }


class LockInIntegration(BaseIntegration):
    name = "lockin"
    interval_seconds = 5 * 60
    required_env = ["LOCKIN_URL", "LOCKIN_TOKEN"]

    def _base(self) -> str:
        return self.settings.lockin_url.rstrip("/")

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        resp = await request(client, "GET", f"{self._base()}{path}", service="Lock-In")
        resp.raise_for_status()
        return resp.json()

    async def fetch(self) -> dict:
        today = today_local()
        version = None
        errors: list[str] = []
        async with make_client(headers=_headers(self.settings.lockin_token)) as client:
            try:
                version = (await self._get(client, "/api/health")).get("version")
            except Exception as exc:
                errors.append(f"health: {describe_error(exc, 'Lock-In')}")
            summary = await self._get(client, "/api/summary")
            export = None
            try:
                export = await self._get(client, "/api/export")
            except Exception as exc:
                errors.append(f"export: {describe_error(exc, 'Lock-In')}")
        data = build_training(summary, export, today, utcnow(), self.settings.lockin_public_url, version)
        if errors:
            raise Degraded(data, "; ".join(errors))
        return data

    def mock(self) -> dict:
        today = today_local()
        delta = today - FIXTURE_ANCHOR
        summary = load_fixture("lockin/summary.json")
        export = load_fixture("lockin/export.json")

        def shift(value: str | None) -> str | None:
            if not value:
                return value
            return (date.fromisoformat(value[:10]) + delta).isoformat()

        summary["today"] = today.isoformat()
        summary["daysUntilGoal"] = max(0, (GOAL_DATE - today).days)
        if summary.get("lastSession"):
            summary["lastSession"]["date"] = shift(summary["lastSession"]["date"])
        if (summary.get("weight") or {}).get("latest"):
            summary["weight"]["latest"]["date"] = shift(summary["weight"]["latest"]["date"])
        for w in export.get("weighIns", []):
            w["date"] = shift(w["date"])
        for s in export.get("sessions", []):
            s["date"] = shift(s["date"])
        # recount the week from the shifted sessions so the squares always match the number
        ws = week_start(today)
        done = [s for s in export["sessions"] if s.get("completedAt") is not None and not s.get("deleted")]
        summary["sessionsThisWeek"] = sum(1 for s in done if ws.isoformat() <= s["date"] <= (ws + timedelta(days=6)).isoformat())
        return build_training(summary, export, today, utcnow(), self.settings.lockin_public_url or "https://lockin.example.ts.net", summary.get("_version", "0.2.1"))
