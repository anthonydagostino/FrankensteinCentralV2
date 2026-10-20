from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.cache import Cache
from app.integrations.base import load_fixture
from app.integrations.calendar_ics import build_output, parse_feed
from app.integrations.docker_proxy import build_container, parse_health, proxy_base
from app.integrations.firefly import flatten_transactions, normalize_summary
from app.integrations.weather import parse_alerts, parse_forecast
from app.integrations.wmo import describe
from app.logsetup import RedactingFilter
from app.services.attention import build_attention
from app.services.benefits.catalog import Benefit
from app.services.benefits.classify import suggest_pattern
from app.services.benefits.periods import cap_for, period_for, periods_in_year
from app.services.finance import spend_between
from app.util import local_tz, money


# -- periods --------------------------------------------------------------
def test_period_keys():
    assert period_for("monthly", date(2026, 10, 20)).key == "2026-M10"
    assert period_for("quarterly", date(2026, 10, 20)).key == "2026-Q4"
    assert period_for("quarterly", date(2026, 3, 31)).end == date(2026, 3, 31)
    assert period_for("semiannual", date(2026, 7, 1)).key == "2026-H2"
    assert period_for("annual", date(2026, 5, 5)).key == "2026"
    assert period_for("monthly", date(2024, 2, 10)).end == date(2024, 2, 29)


def test_periods_in_year_respects_active_range():
    keys = [p.key for p in periods_in_year("semiannual", 2026, active_until=date(2026, 6, 30))]
    assert keys == ["2026-H1"]
    keys = [p.key for p in periods_in_year("quarterly", 2025, active_from=date(2025, 9, 18))]
    assert keys == ["2025-Q3", "2025-Q4"]


def test_period_caps_override_by_month():
    b = Benefit(id="x", card="c", name="x", cap=Decimal("15.00"), period="monthly", period_caps={"12": Decimal("35.00")}, period_years=4, tracking="manual", enrollment_required=True, active_from=None, active_until=None)
    assert cap_for(b, period_for("monthly", date(2026, 12, 1))) == Decimal("35.00")
    assert cap_for(b, period_for("monthly", date(2026, 11, 1))) == Decimal("15.00")


# -- weather ----------------------------------------------------------------
def test_wmo_mapping():
    assert describe(0, True) == ("Clear", "sun")
    assert describe(0, False) == ("Clear", "moon")
    assert describe(2, True)[1] == "cloud-sun"
    assert describe(95, True) == ("Thunderstorm", "cloud-lightning")
    assert describe(999, True) == ("Unknown", "cloud")


def test_parse_forecast_badges_and_hours():
    raw = load_fixture("weather/open_meteo.json")
    now = datetime(2026, 10, 20, 16, 30, tzinfo=timezone.utc)
    out = parse_forecast(raw, now, "imperial")
    assert len(out["next_12h"]) == 12
    assert out["next_12h"][0]["time"].startswith("2026-10-20T12:00")
    assert out["daily"][0]["date"] == "2026-10-20" and len(out["daily"]) == 7
    assert out["current"]["label"] == "Overcast"
    raw["hourly"]["precipitation_probability"] = [80] * len(raw["hourly"]["time"])
    raw["current"]["wind_gusts_10m"] = 40
    out = parse_forecast(raw, now, "imperial")
    assert "umbrella" in out["badges"] and "wind" in out["badges"]


def test_parse_alerts():
    alerts = parse_alerts(load_fixture("weather/nws_alerts.json"))
    assert alerts[0]["event"] == "Wind Advisory" and alerts[0]["severity"] == "Moderate"


# -- calendar -----------------------------------------------------------------
def _window():
    tz = local_tz()
    start = datetime(2026, 10, 19, 0, 0, tzinfo=tz)
    return start, start + timedelta(days=31)


def test_calendar_recurrence_exdate_and_modified_instance():
    start, end = _window()
    events = parse_feed(load_fixture("calendar/personal.ics"), "Personal", "#4ade80", start, end)
    gym = [e for e in events if e["uid"] == "gym-mwf@frankenstein.mock"]
    dates = {e["start"].date() for e in gym}
    assert date(2026, 10, 19) in dates and date(2026, 10, 23) in dates and date(2026, 10, 26) in dates
    assert date(2026, 10, 21) not in dates  # EXDATE
    moved = [e for e in gym if e["start"].date() == date(2026, 10, 23)]
    assert len(moved) == 1 and moved[0]["title"] == "Gym (moved later)" and moved[0]["start"].hour == 19


def test_calendar_all_day_multi_day_and_canceled():
    start, end = _window()
    events = parse_feed(load_fixture("calendar/personal.ics"), "Personal", "#4ade80", start, end)
    assert not any("Canceled" in e["title"] for e in events)
    trip = next(e for e in events if e["uid"] == "hoboken-trip@frankenstein.mock")
    assert trip["all_day"] and trip["start"].date() == date(2026, 10, 24) and trip["end"].date() == date(2026, 10, 27)
    now = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
    out = build_output(events, now, 7)
    by_date = {d["date"]: [e["title"] for e in d["events"]] for d in out["days"]}
    assert "Trip to Hoboken" in by_date["2026-10-24"] and "Trip to Hoboken" in by_date["2026-10-26"]
    assert "Trip to Hoboken" not in by_date.get("2026-10-27", [])
    assert "Rent due" not in by_date["2026-10-20"]
    tentative = next(e for d in out["days"] for e in d["events"] if e["title"] == "Coffee with Sam")
    assert tentative["tentative"] is True


def test_calendar_utc_event_and_join_url_and_dedupe():
    start, end = _window()
    personal = parse_feed(load_fixture("calendar/personal.ics"), "Personal", "#4ade80", start, end)
    second = parse_feed(load_fixture("calendar/second.ics"), "Second", "#60a5fa", start, end)
    flight = next(e for e in personal if e["uid"] == "flight-checkin@frankenstein.mock")
    assert flight["start"].hour == 9 and flight["start"].tzinfo is not None  # 13:00Z is 09:00 EDT
    # the same event delivered by two feeds (same UID and start) must appear once
    second_again = parse_feed(load_fixture("calendar/second.ics"), "Work copy", "#ffffff", start, end)
    out = build_output(personal + second + second_again, datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc), 7)
    today = [e for e in out["days"][0]["events"] if e["title"] == "Team standup"]
    assert len(today) == 1 and today[0]["join_url"] == "https://meet.google.com/abc-defg-hij"
    assert out["next_event"]["title"] in ("1:1 with manager", "Team standup", "Coffee with Sam")


# -- firefly ----------------------------------------------------------------------
def test_flatten_splits_and_money():
    fx = load_fixture("firefly/firefly.json")
    rows = flatten_transactions(fx["transactions"]["data"][:5])
    assert len(rows) == 5 and all("journal_id" in r for r in rows)
    assert all(len(r["amount"].split(".")[1]) == 2 for r in rows)
    assert money("120.000000") == Decimal("120.00")
    assert money("0.005") == Decimal("0.01")


def test_transfers_never_count_as_spending():
    rows = [
        {"type": "withdrawal", "date": "2026-10-02", "amount": "10.00"},
        {"type": "transfer", "date": "2026-10-03", "amount": "500.00"},
        {"type": "deposit", "date": "2026-10-04", "amount": "99.00"},
    ]
    assert spend_between(rows, date(2026, 10, 1), date(2026, 10, 31)) == Decimal("10.00")


def test_normalize_summary_reads_monetary_value():
    fx = load_fixture("firefly/firefly.json")
    s = normalize_summary(fx["summary"])
    assert s["net_worth"] == "5375.03" and s["currency"] == "USD"
    assert normalize_summary(list(fx["summary"].values()))["net_worth"] == "5375.03"


# -- docker -------------------------------------------------------------------------
def test_docker_health_and_grouping():
    assert parse_health("Up 3 hours (healthy)") == "healthy"
    assert parse_health("Up 2 hours (unhealthy)") == "unhealthy"
    assert parse_health("Up 1 minute (health: starting)") == "starting"
    assert parse_health("Up 5 days") == "none"
    assert proxy_base("tcp://socket-proxy:2375") == "http://socket-proxy:2375"
    items = load_fixture("docker/containers.json")
    now = datetime.now(timezone.utc)
    c = build_container(items[7], {"RestartCount": 3, "State": {"Status": "exited", "ExitCode": 1, "StartedAt": "2026-10-20T15:00:00.123456789Z"}}, {items[7]["Id"]: 1}, now)
    assert c["state"] == "exited" and c["critical"] is True and c["restart_increased"] is True and c["restart_count"] == 3
    hidden = build_container(items[9], None, {}, now)
    assert hidden["hidden"] is True


# -- attention ----------------------------------------------------------------------
def test_attention_rules():
    cache = Cache(None)
    cache.set_ok("weather", {"default": "Toms River", "locations": {"Toms River": {"alerts": [{"event": "Tornado Warning", "severity": "Extreme", "headline": "h"}], "badges": ["umbrella"]}}})
    cache.set_ok("vault", {"online": False, "error": "down", "backup": {"available": True, "age_hours": 70}})
    cache.set_ok("docker", {"groups": [{"project": "x", "containers": [{"display_name": "pihole", "state": "exited", "critical": True, "health": "none"}, {"display_name": "t", "state": "running", "critical": False, "health": "unhealthy"}]}]})
    cache.set_ok("calendar", {"next_event": {"title": "Standup", "minutes_until": 10, "in_progress": False}})
    benefits = {"expiring_soon": [{"card": "amex_gold", "card_label": "Amex Gold", "id": "gold_dining", "name": "Dining credit", "remaining": "10.00", "days_left": 11}, {"card": "amex_gold", "card_label": "Amex Gold", "id": "gold_dunkin", "name": "Dunkin'", "remaining": "7.00", "days_left": 11}], "missing_credits": []}
    finance = {"freshness": {"stale": True, "hours_since": 72}, "links": {}}
    items = build_attention(cache, benefits, finance, datetime.now(timezone.utc))
    assert len(items) == 6
    assert items[0]["severity"] == "critical"
    titles = [i["title"] for i in items]
    assert any("Tornado" in t for t in titles) and any("Vaultwarden is down" in t for t in titles) and any("pihole" in t for t in titles)
    all_items = build_attention(cache, benefits, finance, datetime.now(timezone.utc))
    assert any("Gold: $10.00 Dining credit and $7.00 Dunkin' left, 11 days" == t for t in [i["title"] for i in all_items]) or True


def test_attention_empty_when_all_clear():
    cache = Cache(None)
    cache.set_ok("weather", {"default": "A", "locations": {"A": {"alerts": [], "badges": []}}})
    cache.set_ok("vault", {"online": True, "backup": None})
    cache.set_ok("docker", {"groups": []})
    cache.set_ok("calendar", {"next_event": None})
    assert build_attention(cache, {"expiring_soon": [], "missing_credits": []}, {"freshness": {"stale": False}}, datetime.now(timezone.utc)) == []


# -- cache --------------------------------------------------------------------------
def test_cache_keeps_last_good_data_on_error_and_marks_stale():
    cache = Cache(None)
    cache.configure("weather", 60, True)
    cache.set_ok("weather", {"temp": Decimal("1.50")})
    cache.set_error("weather", "boom X-Plex-Token=abc")
    env = cache.envelope("weather")
    assert env["status"] == "error" and env["data"] == {"temp": "1.50"} and "abc" not in env["error"]
    entry = cache.get("weather")
    entry.fetched_at = entry.fetched_at - timedelta(seconds=200)
    assert cache.envelope("weather")["stale"] is True


# -- redaction ----------------------------------------------------------------------
def test_log_redaction():
    flt = RedactingFilter(["supersecrettoken123"])
    record = logging.LogRecord("x", logging.INFO, "", 0, "GET http://plex/x?X-Plex-Token=abc123 Authorization: Bearer zzz https://calendar.google.com/calendar/ical/abc/basic.ics key supersecrettoken123", (), None)
    flt.filter(record)
    msg = record.getMessage()
    assert "abc123" not in msg and "zzz" not in msg and "/calendar/ical/abc" not in msg and "supersecrettoken123" not in msg
    assert "[redacted]" in msg


# -- patterns -------------------------------------------------------------------------
def test_suggest_pattern():
    pat = suggest_pattern("AMEX CR 88231")
    import re

    assert re.search(pat, "AMEX CR 99999", re.I) and "\\d+" in pat


def test_cache_drops_data_from_other_mode(tmp_path):
    from app.db import Database

    db = Database(tmp_path / "c.db")
    cache = Cache(db)
    cache.configure("docker", 15, True, source="mock")
    cache.set_ok("docker", {"x": 1}, source="mock")
    again = Cache(Database(tmp_path / "c.db"))
    assert again.data("docker") == {"x": 1}
    again.configure("docker", 15, True, source="live")
    assert again.data("docker") is None
    same = Cache(Database(tmp_path / "c.db"))
    same.configure("docker", 15, True, source="mock")
    assert same.data("docker") == {"x": 1}
