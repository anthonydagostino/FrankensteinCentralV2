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
    state = build_state(settings, db_path=str(tmp_path_factory.mktemp("db") / "test.db"), start_scheduler=False)
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
    for route in ["/api/weather", "/api/calendar", "/api/finance/summary", "/api/benefits", "/api/plex", "/api/vault", "/api/containers", "/api/attention", "/api/config/public"]:
        assert client.get(route).status_code == 401, route


def test_login_and_envelopes(client):
    r = client.post("/api/auth/login", json={"password": "anything"})
    assert r.status_code == 200 and "fc_session" in r.cookies
    for route in ["/api/weather", "/api/calendar?days=7", "/api/finance/summary", "/api/finance/transactions?limit=5", "/api/cards", "/api/benefits", "/api/benefits/unclassified", "/api/plex", "/api/vault", "/api/containers", "/api/probes", "/api/attention"]:
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
