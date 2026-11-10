from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app, build_state
from app.settings import get_settings


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = get_settings()
    state = build_state(settings, db_path=str(tmp_path_factory.mktemp("db") / "test.db"))
    app.state.fc = state

    async def load():
        for integration in state.integrations.values():
            await state.scheduler.refresh_once(integration)

    asyncio.run(load())
    # no context manager: the lifespan must not run, so the test never touches the real data/ database
    yield TestClient(app)


def test_health_is_public(client):
    assert client.get("/api/health").status_code == 200


def test_unauthenticated_gets_401(client):
    for route in [
        "/api/weather",
        "/api/calendar",
        "/api/finance/summary",
        "/api/benefits",
        "/api/plex",
        "/api/vault",
        "/api/containers",
        "/api/attention",
        "/api/config/public",
    ]:
        assert client.get(route).status_code == 401, route


def test_login_and_envelopes(client):
    r = client.post("/api/auth/login", json={"password": "anything"})
    assert r.status_code == 200 and "fc_session" in r.cookies
    for route in [
        "/api/weather",
        "/api/calendar?days=7",
        "/api/finance/summary",
        "/api/finance/transactions?limit=5",
        "/api/cards",
        "/api/benefits",
        "/api/benefits/unclassified",
        "/api/plex",
        "/api/vault",
        "/api/containers",
        "/api/probes",
        "/api/attention",
    ]:
        r = client.get(route)
        assert r.status_code == 200, route
        body = r.json()
        for key in ("module", "status", "configured", "fetched_at", "stale", "error", "data"):
            assert key in body, (route, key)
        assert body["status"] == "ok" and body["data"] is not None, route


def test_override_and_manual_roundtrip(client):
    client.post("/api/auth/login", json={"password": "x"})
    unclassified = client.get("/api/benefits/unclassified").json()["data"]["items"]
    target = next(i for i in unclassified if i["description"] == "AMEX CR 88231")
    r = client.post("/api/benefits/overrides", json={"journal_id": target["journal_id"], "classification": "statement_credit", "benefit_id": "plat_walmart"})
    assert r.status_code == 200
    after = client.get("/api/benefits/unclassified").json()["data"]
    assert all(i["journal_id"] != target["journal_id"] for i in after["items"])
    override_id = after["overrides"][0]["id"]
    assert client.delete(f"/api/benefits/overrides/{override_id}").status_code == 200
    r = client.post("/api/benefits/manual", json={"benefit_id": "plat_uber_cash", "period_key": "2026-M12", "amount": "35"})
    assert r.status_code == 200 and r.json()["amount"] == "35.00"


def test_kiosk_cookie_is_read_only(client):
    kiosk = TestClient(app)
    r = kiosk.get("/kiosk?token=" + os.environ["KIOSK_TOKEN"], follow_redirects=False)
    assert r.status_code == 303 and "fc_kiosk" in r.cookies
    assert kiosk.get("/api/weather").status_code == 200
    assert kiosk.post("/api/benefits/manual", json={"benefit_id": "plat_uber_cash", "period_key": "2026-M12"}).status_code == 403
    bad = TestClient(app)
    r = bad.get("/kiosk?token=wrong", follow_redirects=False)
    assert "fc_kiosk" not in r.cookies


def test_rotating_kiosk_token_revokes_issued_cookies(client, monkeypatch):
    from app.settings import get_settings

    kiosk = TestClient(app)
    kiosk.get("/kiosk?token=" + os.environ["KIOSK_TOKEN"], follow_redirects=False)
    assert kiosk.get("/api/weather").status_code == 200
    monkeypatch.setattr(get_settings(), "kiosk_token", "a-brand-new-kiosk-token-0987654321")
    assert kiosk.get("/api/weather").status_code == 401, "a cookie issued for the old KIOSK_TOKEN no longer authenticates"


def test_public_config_links_never_resolve_non_url_env(client, monkeypatch):
    from app.config_loader import LinkTile

    client.post("/api/auth/login", json={"password": "x"})
    state = app.state.fc
    monkeypatch.setenv("FIREFLY_TOKEN", "super-secret-token-value")
    monkeypatch.setenv("WIKI_URL", "https://wiki.example.test")
    monkeypatch.setattr(state.config, "links", [LinkTile(name="Leak", env_url="FIREFLY_TOKEN"), LinkTile(name="Wiki", env_url="WIKI_URL")])
    links = client.get("/api/config/public").json()["links"]
    assert [link["name"] for link in links] == ["Wiki"]
    assert "super-secret-token-value" not in str(links)


def test_plex_image_rejects_non_library_paths(client):
    client.post("/api/auth/login", json={"password": "x"})
    assert client.get("/api/plex/image?path=/etc/passwd").status_code == 400
    r = client.get("/api/plex/image?path=/library/metadata/1/thumb/1")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")


def test_restart_forbidden_by_default(client):
    client.post("/api/auth/login", json={"password": "x"})
    assert client.post("/api/containers/abc/restart").status_code == 403


def test_no_token_in_plex_response(client):
    client.post("/api/auth/login", json={"password": "x"})
    body = client.get("/api/plex").text
    assert "X-Plex-Token" not in body


def test_recurring_route_and_ignore(client):
    client.post("/api/auth/login", json={"password": "x"})
    body = client.get("/api/finance/recurring").json()
    assert body["module"] == "recurring" and body["status"] == "ok"
    items = body["data"]["items"]
    netflix = next(i for i in items if "NETFLIX" in i["key"])
    assert netflix["price_increase"] is True
    before = body["data"]["totals"]["active_count"]
    r = client.post("/api/finance/recurring/ignore", json={"key": netflix["key"], "ignore": True})
    assert r.status_code == 200
    after = client.get("/api/finance/recurring").json()["data"]
    assert after["totals"]["active_count"] == before - 1
    assert next(i for i in after["items"] if i["key"] == netflix["key"])["ignored"] is True
    client.post("/api/finance/recurring/ignore", json={"key": netflix["key"], "ignore": False})
    attention = client.get("/api/attention").json()["data"]["items"]
    assert any(a["source"] == "recurring" for a in attention)


def test_lockin_route(client):
    client.post("/api/auth/login", json={"password": "x"})
    body = client.get("/api/lockin").json()
    assert body["module"] == "lockin" and body["status"] == "ok"
    assert body["data"]["next_session"]["name"] and len(body["data"]["week"]) == 7
    assert "tok" not in client.get("/api/lockin").text


def test_derived_views_are_memoized_per_year_and_invalidated(client):
    state = app.state.fc
    state.invalidate_benefits()
    this_year = state.benefits()
    last_year = state.benefits(this_year["year"] - 1)
    assert state.benefits() is this_year, "alternating years must not evict each other"
    assert state.benefits(this_year["year"] - 1) is last_year
    assert state.finance_summary() is state.finance_summary()
    assert state.recurring() is state.recurring()
    before = state.recurring()
    key = (before["items"] or [{"key": "none"}])[0]["key"]
    state.set_recurring_ignored(key, True)
    assert state.recurring() is not before, "changing the ignore list recomputes the recurring view"
    assert state.benefits() is not this_year, "any override change clears every derived view"
    state.set_recurring_ignored(key, False)
