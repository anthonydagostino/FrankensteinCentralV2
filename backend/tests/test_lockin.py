from __future__ import annotations

import copy
from datetime import date, datetime, timezone

import httpx
import pytest
import respx

from app.cache import Cache
from app.config_loader import get_dashboard_config
from app.integrations.base import Degraded, TokenRejected, load_fixture
from app.integrations.lockin import LockInIntegration, build_training
from app.services.attention import build_attention
from app.settings import Settings

NOW = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)


def settings(**overrides) -> Settings:
    base = dict(mock_mode=False, lockin_url="http://lockin:8080", lockin_token="tok", lockin_public_url="https://lockin.ts.net")
    base.update(overrides)
    return Settings(_env_file=None, **base)


def summary(**overrides) -> dict:
    s = copy.deepcopy(load_fixture("lockin/summary.json"))
    s.update(overrides)
    return s


def test_streak_risk_states():
    sun = date(2026, 10, 25)  # Sunday: one day left in the week
    assert build_training(summary(sessionsThisWeek=4), None, sun, NOW, None, None)["streak_risk"] == "at_risk"
    assert build_training(summary(sessionsThisWeek=5), None, sun, NOW, None, None)["streak_risk"] == "safe"
    assert build_training(summary(sessionsThisWeek=3), None, sun, NOW, None, None)["streak_risk"] == "lost"
    mon = date(2026, 10, 19)
    out = build_training(summary(sessionsThisWeek=0), None, mon, NOW, None, None)
    assert out["streak_risk"] == "ok" and out["days_left_in_week"] == 7 and out["sessions_needed_for_streak"] == 5


def test_week_squares_and_weight_series_from_export():
    export = load_fixture("lockin/export.json")
    out = build_training(summary(), export, date(2026, 10, 25), NOW, "https://x", "0.2.1")
    assert [d["label"] for d in out["week"]] == list("MTWTFSS")
    assert [d["done"] for d in out["week"]] == [True, True, False, True, True, False, False]
    assert out["week"][6]["today"] is True and out["week"][0]["date"] == "2026-10-19"
    assert out["weight_series"][-1]["date"] == "2026-10-25" and len(out["weight_series"]) > 40
    assert out["weighed_today"] is True and out["trained_today"] is False
    assert out["weight"]["on_track"] is False  # +1.4 vs +0.5 target
    assert out["public_url"] == "https://x" and out["version"] == "0.2.1"


def test_without_export_still_builds():
    out = build_training(summary(), None, date(2026, 10, 25), NOW, None, None)
    assert out["week"] is None and out["weight_series"] is None
    assert out["next_session"]["name"] == "Legs A" and out["days_until_goal"] == 219


@respx.mock
async def test_fetch_live():
    respx.get("http://lockin:8080/api/health").mock(return_value=httpx.Response(200, json=load_fixture("lockin/health.json")))
    summ = respx.get("http://lockin:8080/api/summary").mock(return_value=httpx.Response(200, json=load_fixture("lockin/summary.json")))
    respx.get("http://lockin:8080/api/export").mock(return_value=httpx.Response(200, json=load_fixture("lockin/export.json")))
    data = await LockInIntegration(settings(), get_dashboard_config()).fetch()
    assert summ.calls.last.request.headers["Authorization"] == "Bearer tok"
    assert data["version"] == "0.2.1" and data["week"] is not None and data["public_url"] == "https://lockin.ts.net"


@respx.mock
async def test_fetch_token_rejected():
    respx.get("http://lockin:8080/api/health").mock(return_value=httpx.Response(200, json=load_fixture("lockin/health.json")))
    respx.get("http://lockin:8080/api/summary").mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
    with pytest.raises(TokenRejected):
        await LockInIntegration(settings(), get_dashboard_config()).fetch()


@respx.mock
async def test_fetch_degraded_without_export():
    respx.get("http://lockin:8080/api/health").mock(return_value=httpx.Response(200, json=load_fixture("lockin/health.json")))
    respx.get("http://lockin:8080/api/summary").mock(return_value=httpx.Response(200, json=load_fixture("lockin/summary.json")))
    respx.get("http://lockin:8080/api/export").mock(return_value=httpx.Response(500))
    with pytest.raises(Degraded) as exc:
        await LockInIntegration(settings(), get_dashboard_config()).fetch()
    assert exc.value.data["next_session"]["name"] == "Legs A" and exc.value.data["week"] is None


def test_attention_rules_for_training():
    cache = Cache(None)
    cache.configure("lockin", 300, True)
    cache.set_ok("lockin", {"streak_risk": "at_risk", "sessions_needed_for_streak": 1, "days_left_in_week": 1, "next_session": {"name": "Legs A"}, "weighed_today": False, "phase": {"deload": True}, "public_url": "https://lockin.ts.net", "streak_weeks": 4})
    items = build_attention(cache, None, None, NOW)  # 16:00 UTC is noon in New York
    titles = [i["title"] for i in items]
    assert "Streak at risk: 1 session in 1 day" in titles
    assert "Log your weight" in titles and "Deload week" in titles
    assert all(i["link"] == "https://lockin.ts.net" for i in items if i["source"] == "lockin")
    cache.set_ok("lockin", {"streak_risk": "lost", "sessions_needed_for_streak": 2, "days_left_in_week": 1, "sessions_this_week": 3, "streak_min_sessions": 5, "streak_weeks": 4, "weighed_today": True, "phase": {"deload": False}})
    titles = [i["title"] for i in build_attention(cache, None, None, NOW)]
    assert "4 week streak ends this week" in titles and "Log your weight" not in titles
    # before 10 AM local there is no weigh-in nag
    early = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)  # 8 AM New York
    cache.set_ok("lockin", {"streak_risk": "ok", "weighed_today": False, "phase": {}})
    assert build_attention(cache, None, None, early) == []
