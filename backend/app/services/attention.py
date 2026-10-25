"""Builds the attention strip from every cached module."""

from __future__ import annotations

from datetime import datetime

from ..util import local_tz as _local_tz

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
MAX_ITEMS = 6


def _item(severity: str, icon: str, title: str, detail: str | None, link: str | None, source: str, ts: str | None = None) -> dict:
    return {"severity": severity, "icon": icon, "title": title, "detail": detail, "link": link, "source": source, "time": ts}


def build_attention(cache, benefits: dict | None, finance_summary: dict | None, now: datetime, location: str | None = None, recurring: dict | None = None) -> list[dict]:
    items: list[dict] = []

    # Weather alerts and badges
    weather = cache.data("weather") or {}
    locs = weather.get("locations") or {}
    loc = locs.get(location or weather.get("default") or "", None) or (next(iter(locs.values())) if locs else None)
    if loc:
        for alert in loc.get("alerts") or []:
            sev = alert.get("severity")
            if sev in ("Extreme", "Severe"):
                items.append(_item("critical", "triangle-alert", alert.get("event") or "Weather alert", alert.get("headline"), None, "weather", alert.get("effective")))
            elif sev == "Moderate":
                items.append(_item("warning", "cloud-alert", alert.get("event") or "Weather alert", alert.get("headline"), None, "weather", alert.get("effective")))
        if "umbrella" in (loc.get("badges") or []):
            items.append(_item("info", "umbrella", "Umbrella today", "Rain likely in the next 12 hours", None, "weather"))

    # Vaultwarden
    vault_entry = cache.get("vault")
    vault = cache.data("vault") or {}
    if vault_entry and vault_entry.status not in ("disabled",):
        if vault_entry.status == "error" or vault.get("online") is False:
            items.append(_item("critical", "shield-off", "Vaultwarden is down", vault.get("error") or vault_entry.error, vault.get("public_url"), "vault"))
        backup = vault.get("backup") or {}
        if backup.get("available") and backup.get("age_hours") is not None and backup["age_hours"] > 48:
            items.append(_item("warning", "database-backup", "Vaultwarden backup is old", f"Newest backup is {backup['age_hours']:.0f} hours old", None, "vault"))

    # Containers
    docker = cache.data("docker") or {}
    for group in docker.get("groups") or []:
        for c in group.get("containers") or []:
            if c.get("critical") and c.get("state") != "running":
                items.append(_item("critical", "container", f"{c['display_name']} is {c['state']}", c.get("status"), c.get("url") or docker.get("portainer_url"), "containers"))
            elif c.get("health") == "unhealthy":
                items.append(_item("warning", "heart-pulse", f"{c['display_name']} is unhealthy", c.get("status"), c.get("url") or docker.get("portainer_url"), "containers"))

    # Benefits
    if benefits:
        per_card: dict[str, list[dict]] = {}
        for e in benefits.get("expiring_soon") or []:
            per_card.setdefault(e["card_label"], []).append(e)
        for label, entries in per_card.items():
            parts = [f"${e['remaining']} {e['name']}" for e in entries]
            days = min(e["days_left"] for e in entries)
            short = label.replace("Amex ", "")
            items.append(_item("warning", "badge-dollar-sign", f"{short}: {' and '.join(parts[:3])} left, {days} days", None, "/benefits", "benefits"))
        for m in benefits.get("missing_credits") or []:
            items.append(_item("warning", "circle-help", f"{m['card_label'].replace('Amex ', '')}: missing {m['name']} credit", m["message"], "/benefits", "benefits"))

    # Finance freshness
    if finance_summary:
        fresh = finance_summary.get("freshness") or {}
        if fresh.get("stale"):
            items.append(_item("warning", "database-zap", "Finance data looks stale", f"Newest bank transaction is {fresh.get('hours_since', 0):.0f} hours old, check the SimpleFIN import", finance_summary.get("links", {}).get("home"), "finance"))

    # Lock-In training
    lockin_entry = cache.get("lockin")
    lockin = cache.data("lockin") or {}
    if lockin_entry and lockin_entry.status not in ("disabled",) and lockin:
        link = lockin.get("public_url")
        risk = lockin.get("streak_risk")
        needed = lockin.get("sessions_needed_for_streak") or 0
        if risk == "at_risk" and needed > 0:
            items.append(_item("warning", "dumbbell", f"Streak at risk: {needed} session{'s' if needed > 1 else ''} in {lockin.get('days_left_in_week')} day{'s' if lockin.get('days_left_in_week', 0) > 1 else ''}", f"Next up: {(lockin.get('next_session') or {}).get('name', '')}", link, "lockin"))
        elif risk == "lost" and (lockin.get("streak_weeks") or 0) > 0:
            items.append(_item("warning", "dumbbell", f"{lockin.get('streak_weeks')} week streak ends this week", f"{lockin.get('sessions_this_week')} of {lockin.get('streak_min_sessions')} sessions, {lockin.get('days_left_in_week')} days left", link, "lockin"))
        local_hour = now.astimezone(_local_tz()).hour
        if not lockin.get("weighed_today") and 10 <= local_hour < 22:
            items.append(_item("info", "scale", "Log your weight", "No weigh-in yet today", link, "lockin"))
        if (lockin.get("phase") or {}).get("deload"):
            items.append(_item("info", "dumbbell", "Deload week", "Half the sets, stop 4 reps short of failure", link, "lockin"))

    # Recurring charges: a price increase is the one thing worth interrupting for
    if recurring:
        bumps = [r for r in recurring.get("items") or [] if r.get("price_increase") and not r.get("ignored") and r.get("status") == "active"]
        for r in bumps[:2]:
            items.append(_item("warning", "receipt", f"{r['name']} went up to ${r['amount']}", f"Was ${r['previous_amount']} per {r['cadence'].replace('ly', '') if r['cadence'] != 'monthly' else 'month'}", r.get("url") or "/", "recurring"))

    # Calendar
    cal = cache.data("calendar") or {}
    nxt = cal.get("next_event")
    if nxt and not nxt.get("in_progress") and nxt.get("minutes_until", 999) <= 30:
        items.append(_item("info", "calendar-clock", f"{nxt['title']} in {nxt['minutes_until']} min", nxt.get("location"), nxt.get("join_url"), "calendar", nxt.get("start")))
    elif nxt and nxt.get("in_progress"):
        items.append(_item("info", "calendar-check", f"Now: {nxt['title']}", nxt.get("location"), nxt.get("join_url"), "calendar", nxt.get("start")))

    items.sort(key=lambda i: (SEVERITY_RANK.get(i["severity"], 9), i.get("time") or ""))
    return items[:MAX_ITEMS]
