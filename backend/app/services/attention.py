"""Builds the attention strip from every cached module."""

from __future__ import annotations

from datetime import datetime

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
MAX_ITEMS = 6


def _item(severity: str, icon: str, title: str, detail: str | None, link: str | None, source: str, ts: str | None = None) -> dict:
    return {"severity": severity, "icon": icon, "title": title, "detail": detail, "link": link, "source": source, "time": ts}


def build_attention(cache, benefits: dict | None, finance_summary: dict | None, now: datetime, location: str | None = None) -> list[dict]:
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

    # Calendar
    cal = cache.data("calendar") or {}
    nxt = cal.get("next_event")
    if nxt and not nxt.get("in_progress") and nxt.get("minutes_until", 999) <= 30:
        items.append(_item("info", "calendar-clock", f"{nxt['title']} in {nxt['minutes_until']} min", nxt.get("location"), nxt.get("join_url"), "calendar", nxt.get("start")))
    elif nxt and nxt.get("in_progress"):
        items.append(_item("info", "calendar-check", f"Now: {nxt['title']}", nxt.get("location"), nxt.get("join_url"), "calendar", nxt.get("start")))

    items.sort(key=lambda i: (SEVERITY_RANK.get(i["severity"], 9), i.get("time") or ""))
    return items[:MAX_ITEMS]
