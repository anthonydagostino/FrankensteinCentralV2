"""Google Calendar via secret iCal feeds (read-only), parsed with icalendar + recurring-ical-events."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import recurring_ical_events
from icalendar import Calendar

from ..util import iso, local_tz, strip_html, utcnow
from .base import BaseIntegration, Degraded, describe_error, load_fixture, make_client, request

log = logging.getLogger("frankenstein.calendar")

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
JOIN_HINTS = ("zoom.us", "meet.google.com", "teams.microsoft.com", "webex.com", "gotomeeting", "whereby.com")


def _as_aware(value: Any, tz) -> datetime | None:
    """Convert an icalendar DTSTART/DTEND value to an aware datetime in the local zone."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(tz)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=tz)
    return None


def _first_url(*texts: str | None) -> str | None:
    candidates: list[str] = []
    for text in texts:
        if not text:
            continue
        candidates.extend(URL_RE.findall(text))
    if not candidates:
        return None
    for c in candidates:
        if any(h in c.lower() for h in JOIN_HINTS):
            return c.rstrip(".,;")
    return candidates[0].rstrip(".,;")


def parse_feed(ics_text: str, feed_name: str, color: str, window_start: datetime, window_end: datetime) -> list[dict]:
    """Expand one iCal feed into event dicts within the window. Canceled events are skipped."""
    tz = local_tz()
    cal = Calendar.from_ical(ics_text)
    events: list[dict] = []
    for ev in recurring_ical_events.of(cal, components=["VEVENT"]).between(window_start, window_end):
        status = str(ev.get("STATUS", "")).upper()
        if status == "CANCELLED":
            continue
        dtstart = ev.get("DTSTART")
        dtend = ev.get("DTEND")
        if dtstart is None:
            continue
        start_val = dtstart.dt
        all_day = isinstance(start_val, date) and not isinstance(start_val, datetime)
        start = _as_aware(start_val, tz)
        if start is None:
            continue
        if dtend is not None:
            end = _as_aware(dtend.dt, tz)
        else:
            duration = ev.get("DURATION")
            if duration is not None:
                end = start + duration.dt
            else:
                end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
        if end is None or end <= start:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
        uid = str(ev.get("UID", ""))
        summary = str(ev.get("SUMMARY", "(no title)"))
        location = str(ev.get("LOCATION", "") or "")
        description = strip_html(str(ev.get("DESCRIPTION", "") or ""))
        events.append(
            {
                "id": f"{uid}:{start.isoformat()}",
                "uid": uid,
                "title": summary,
                "start": start,
                "end": end,
                "all_day": all_day,
                "calendar": feed_name,
                "color": color,
                "location": location or None,
                "description": description[:2000] or None,
                "join_url": _first_url(location, description),
                "tentative": status == "TENTATIVE",
            }
        )
    return events


def build_output(all_events: list[dict], now: datetime, lookahead_days: int) -> dict:
    tz = local_tz()
    local_now = now.astimezone(tz)
    today = local_now.date()

    # de-duplicate across feeds: same UID and same start
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for ev in sorted(all_events, key=lambda e: (e["start"], e["title"])):
        key = (ev["uid"], ev["start"].isoformat())
        if key in seen:
            continue
        seen.add(key)
        unique.append(ev)

    days: list[dict] = []
    density: dict[str, int] = {}
    for offset in range(lookahead_days):
        day = today + timedelta(days=offset)
        day_start = datetime.combine(day, time.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        day_events = [e for e in unique if e["start"] < day_end and e["end"] > day_start]
        day_events.sort(key=lambda e: (not e["all_day"], e["start"]))
        label = "Today" if offset == 0 else "Tomorrow" if offset == 1 else day.strftime("%A")
        serialized = []
        for e in day_events:
            serialized.append(
                {
                    "id": e["id"],
                    "title": e["title"],
                    "start": iso(e["start"]),
                    "end": iso(e["end"]),
                    "all_day": e["all_day"],
                    "multi_day": e["all_day"] and (e["end"] - e["start"]) > timedelta(days=1) or (not e["all_day"] and e["end"].date() != e["start"].date()),
                    "calendar": e["calendar"],
                    "color": e["color"],
                    "location": e["location"],
                    "description": e["description"],
                    "join_url": e["join_url"],
                    "tentative": e["tentative"],
                    "in_progress": e["start"] <= local_now < e["end"],
                }
            )
        if day_events:
            density[day.isoformat()] = len(day_events)
        days.append({"date": day.isoformat(), "label": label, "events": serialized})

    next_event = None
    current = next((e for e in unique if not e["all_day"] and e["start"] <= local_now < e["end"]), None)
    upcoming = next((e for e in unique if not e["all_day"] and e["start"] > local_now), None)
    chosen = current or upcoming
    if chosen is not None:
        minutes = int((chosen["start"] - local_now).total_seconds() // 60)
        next_event = {
            "title": chosen["title"],
            "start": iso(chosen["start"]),
            "end": iso(chosen["end"]),
            "minutes_until": max(minutes, 0),
            "in_progress": chosen is current,
            "calendar": chosen["calendar"],
            "color": chosen["color"],
            "join_url": chosen["join_url"],
            "location": chosen["location"],
        }

    return {"now": iso(local_now), "next_event": next_event, "days": days, "month_density": density}


class CalendarIntegration(BaseIntegration):
    name = "calendar"
    interval_seconds = 5 * 60

    def __init__(self, settings, config):
        super().__init__(settings, config)
        self._conditional: dict[str, dict[str, str]] = {}  # feed name -> {etag, last_modified, body}

    def _feeds(self) -> list[tuple[str, str, str]]:
        out = []
        for feed in self.config.calendar.feeds:
            url = self.settings.env_value(feed.env) or getattr(self.settings, feed.env.lower(), "")
            if url:
                out.append((feed.name, feed.color, url))
        return out

    def is_configured(self) -> bool:
        return bool(self._feeds())

    def setup_hint(self) -> list[str]:
        return [f.env for f in self.config.calendar.feeds] or ["GCAL_ICS_PRIMARY"]

    def _window(self, now: datetime) -> tuple[datetime, datetime]:
        tz = local_tz()
        local = now.astimezone(tz)
        start = datetime.combine(local.date() - timedelta(days=1), time.min, tzinfo=tz)
        end = local + timedelta(days=self.config.calendar.lookahead_days + 1)
        return start, end

    async def _download(self, client, name: str, url: str) -> str:
        state = self._conditional.get(name, {})
        headers = {}
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            headers["If-Modified-Since"] = state["last_modified"]
        resp = await request(client, "GET", url, headers=headers, service=f"calendar feed {name}")
        if resp.status_code == 304 and state.get("body"):
            return state["body"]
        resp.raise_for_status()
        body = resp.text
        self._conditional[name] = {"etag": resp.headers.get("ETag", ""), "last_modified": resp.headers.get("Last-Modified", ""), "body": body}
        return body

    async def fetch(self) -> dict:
        now = utcnow()
        w_start, w_end = self._window(now)
        events: list[dict] = []
        errors: list[str] = []
        async with make_client(timeout=20.0) as client:
            for name, color, url in self._feeds():
                try:
                    body = await self._download(client, name, url)
                    events.extend(parse_feed(body, name, color, w_start, w_end))
                except Exception as exc:
                    errors.append(f"{name}: {describe_error(exc, 'calendar feed')}")
        data = build_output(events, now, self.config.calendar.lookahead_days)
        data["feeds"] = [{"name": n, "color": c} for n, c, _ in self._feeds()]
        if errors and len(errors) == len(self._feeds()):
            raise RuntimeError("; ".join(errors))
        if errors:
            raise Degraded(data, "; ".join(errors))
        return data

    def mock(self) -> dict:
        now = utcnow()
        w_start, w_end = self._window(now)
        feeds = self.config.calendar.feeds or []
        fixture_files = ["calendar/personal.ics", "calendar/second.ics"]
        events: list[dict] = []
        feed_meta = []
        for idx, fname in enumerate(fixture_files):
            if idx < len(feeds):
                name, color = feeds[idx].name, feeds[idx].color
            else:
                name, color = ("Personal", "#4ade80") if idx == 0 else ("Second", "#60a5fa")
            feed_meta.append({"name": name, "color": color})
            events.extend(parse_feed(load_fixture(fname), name, color, w_start, w_end))
        data = build_output(events, now, self.config.calendar.lookahead_days)
        data["feeds"] = feed_meta
        return data
