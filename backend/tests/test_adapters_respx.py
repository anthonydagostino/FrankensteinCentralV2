"""Live adapters exercised against recorded fixtures with respx."""

from __future__ import annotations

import copy
import json

import httpx
import pytest
import respx

from app.config_loader import get_dashboard_config
from app.integrations.base import Degraded, TokenRejected, load_fixture
from app.integrations.calendar_ics import CalendarIntegration
from app.integrations.docker_proxy import DockerIntegration
from app.integrations.firefly import FireflyIntegration, add_tags_to_group
from app.integrations.plex import PlexIntegration
from app.integrations.vaultwarden import VaultwardenIntegration
from app.integrations.weather import WeatherIntegration
from app.settings import Settings


def settings(**overrides) -> Settings:
    base = dict(
        mock_mode=False,
        firefly_url="http://firefly:8080",
        firefly_token="tok",
        plex_url="http://plex:32400",
        plex_token="ptok",
        vaultwarden_url="http://vault:80",
        docker_host="tcp://socket-proxy:2375",
        gcal_ics_primary="https://calendar.google.com/calendar/ical/abc/basic.ics",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@respx.mock
async def test_firefly_pagination_and_flatten():
    fx = load_fixture("firefly/firefly.json")
    groups = fx["transactions"]["data"]
    half = len(groups) // 2
    page1 = {"data": groups[:half], "meta": {"pagination": {"total_pages": 2, "current_page": 1}}}
    page2 = {"data": groups[half:], "meta": {"pagination": {"total_pages": 2, "current_page": 2}}}

    def tx_route(request):
        page = int(request.url.params.get("page", "1"))
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json=page1 if page == 1 else page2)

    respx.get("http://firefly:8080/api/v1/about").mock(return_value=httpx.Response(200, json=fx["about"]))
    respx.get("http://firefly:8080/api/v1/accounts").mock(
        side_effect=lambda r: httpx.Response(
            200, json=fx["accounts"] if r.url.params.get("type") == "asset" else {"data": [], "meta": {"pagination": {"total_pages": 1}}}
        )
    )
    respx.get("http://firefly:8080/api/v1/transactions").mock(side_effect=tx_route)
    respx.get("http://firefly:8080/api/v1/summary/basic").mock(return_value=httpx.Response(200, json=fx["summary"]))
    respx.get("http://firefly:8080/api/v1/insight/expense/category").mock(return_value=httpx.Response(200, json=fx["insight_category"]))
    respx.get("http://firefly:8080/api/v1/insight/expense/expense").mock(return_value=httpx.Response(200, json=fx["insight_expense"]))
    respx.get("http://firefly:8080/api/v1/budgets").mock(return_value=httpx.Response(200, json={**fx["budgets"], "meta": {"pagination": {"total_pages": 1}}}))
    respx.get(url__regex=r"http://firefly:8080/api/v1/budgets/\d+/limits").mock(
        side_effect=lambda r: httpx.Response(200, json={"data": fx["budget_limits"][r.url.path.split("/")[-2]]})
    )
    respx.get("http://firefly:8080/api/v1/bills").mock(return_value=httpx.Response(200, json={**fx["bills"], "meta": {"pagination": {"total_pages": 1}}}))

    data = await FireflyIntegration(settings(), get_dashboard_config()).fetch()
    assert len(data["transactions"]) == len(groups)
    assert data["about"]["version"] == "6.1.25"
    assert any(a["name"] == "Amex Platinum" for a in data["accounts"])
    assert data["summary"]["net_worth"] == "5375.03"


@respx.mock
async def test_firefly_token_rejected():
    respx.get("http://firefly:8080/api/v1/about").mock(return_value=httpx.Response(401, json={"message": "Unauthenticated"}))
    with pytest.raises(TokenRejected) as exc:
        await FireflyIntegration(settings(), get_dashboard_config()).fetch()
    assert "regenerate" in str(exc.value)


@respx.mock
async def test_firefly_degraded_when_insights_fail():
    fx = load_fixture("firefly/firefly.json")
    respx.get("http://firefly:8080/api/v1/about").mock(return_value=httpx.Response(200, json=fx["about"]))
    respx.get("http://firefly:8080/api/v1/accounts").mock(return_value=httpx.Response(200, json=fx["accounts"]))
    respx.get("http://firefly:8080/api/v1/transactions").mock(return_value=httpx.Response(200, json={"data": [], "meta": {"pagination": {"total_pages": 1}}}))
    respx.get("http://firefly:8080/api/v1/summary/basic").mock(return_value=httpx.Response(500))
    respx.get(url__regex=r"http://firefly:8080/api/v1/insight/.*").mock(return_value=httpx.Response(500))
    respx.get("http://firefly:8080/api/v1/budgets").mock(return_value=httpx.Response(200, json={"data": [], "meta": {"pagination": {"total_pages": 1}}}))
    respx.get("http://firefly:8080/api/v1/bills").mock(return_value=httpx.Response(200, json={"data": [], "meta": {"pagination": {"total_pages": 1}}}))
    with pytest.raises(Degraded) as exc:
        await FireflyIntegration(settings(), get_dashboard_config()).fetch()
    assert "summary" in exc.value.message and exc.value.data["accounts"]


@respx.mock
async def test_firefly_tag_writeback_keeps_splits_and_tags():
    group = {
        "data": {
            "id": "77",
            "attributes": {
                "group_title": None,
                "transactions": [
                    {
                        "transaction_journal_id": "1",
                        "type": "deposit",
                        "date": "2026-10-06T00:00:00-04:00",
                        "amount": "75.00",
                        "description": "CREDIT",
                        "source_id": "9",
                        "destination_id": "3",
                        "tags": ["existing"],
                    },
                    {
                        "transaction_journal_id": "2",
                        "type": "deposit",
                        "date": "2026-10-06T00:00:00-04:00",
                        "amount": "1.00",
                        "description": "OTHER",
                        "source_id": "9",
                        "destination_id": "3",
                        "tags": [],
                    },
                ],
            },
        }
    }
    respx.get("http://firefly:8080/api/v1/transactions/77").mock(return_value=httpx.Response(200, json=group))
    put = respx.put("http://firefly:8080/api/v1/transactions/77").mock(return_value=httpx.Response(200, json=group))
    changed = await add_tags_to_group(settings(), "77", 1, ["amex-credit", "benefit:plat_lululemon:2026-Q4"])
    assert changed
    body = json.loads(put.calls.last.request.content)
    assert len(body["transactions"]) == 2
    assert body["transactions"][0]["tags"] == ["existing", "amex-credit", "benefit:plat_lululemon:2026-Q4"]
    assert body["transactions"][1]["tags"] == []


@respx.mock
async def test_weather_nws_failure_is_degraded():
    respx.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(200, json=load_fixture("weather/open_meteo.json")))
    respx.get("https://air-quality-api.open-meteo.com/v1/air-quality").mock(return_value=httpx.Response(200, json={"current": {"us_aqi": 30}}))
    respx.get("https://api.weather.gov/alerts/active").mock(return_value=httpx.Response(503))
    with pytest.raises(Degraded) as exc:
        await WeatherIntegration(settings(), get_dashboard_config()).fetch()
    data = exc.value.data
    assert data["locations"]["Toms River"]["current"]["temp"] == 58
    assert data["locations"]["Toms River"]["alerts"] == []


@respx.mock
async def test_weather_sends_user_agent_to_nws():
    respx.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(200, json=load_fixture("weather/open_meteo.json")))
    respx.get("https://air-quality-api.open-meteo.com/v1/air-quality").mock(return_value=httpx.Response(200, json={"current": {"us_aqi": 30}}))
    nws = respx.get("https://api.weather.gov/alerts/active").mock(return_value=httpx.Response(200, json=load_fixture("weather/nws_alerts.json")))
    data = await WeatherIntegration(settings(nws_user_agent="(Test, me@example.com)"), get_dashboard_config()).fetch()
    assert nws.calls.last.request.headers["User-Agent"] == "(Test, me@example.com)"
    assert data["locations"]["Toms River"]["alerts"][0]["event"] == "Wind Advisory"


@respx.mock
async def test_calendar_one_feed_failing_is_degraded():
    route = respx.get("https://calendar.google.com/calendar/ical/abc/basic.ics").mock(
        return_value=httpx.Response(200, text=load_fixture("calendar/personal.ics"), headers={"ETag": "v1"})
    )
    respx.get("https://calendar.google.com/calendar/ical/def/basic.ics").mock(return_value=httpx.Response(500))
    integration = CalendarIntegration(settings(gcal_ics_second="https://calendar.google.com/calendar/ical/def/basic.ics"), get_dashboard_config())
    with pytest.raises(Degraded) as exc:
        await integration.fetch()
    assert exc.value.data["days"]
    # conditional request on the second pass
    route.mock(return_value=httpx.Response(304))
    with pytest.raises(Degraded):
        await integration.fetch()
    assert route.calls.last.request.headers["If-None-Match"] == "v1"


@respx.mock
async def test_plex_fetch_uses_header_token_and_proxies_posters():
    respx.get("http://plex:32400/identity").mock(return_value=httpx.Response(200, json=load_fixture("plex/identity.json")))
    sessions = respx.get("http://plex:32400/status/sessions").mock(return_value=httpx.Response(200, json=load_fixture("plex/sessions.json")))
    respx.get("http://plex:32400/library/recentlyAdded").mock(return_value=httpx.Response(200, json=load_fixture("plex/recently_added.json")))
    respx.get("http://plex:32400/library/onDeck").mock(return_value=httpx.Response(200, json=load_fixture("plex/on_deck.json")))
    respx.get("http://plex:32400/library/sections").mock(return_value=httpx.Response(200, json=load_fixture("plex/sections.json")))
    respx.get(url__regex=r"http://plex:32400/library/sections/\d+/all").mock(return_value=httpx.Response(200, json={"MediaContainer": {"totalSize": 5}}))
    data = await PlexIntegration(settings(), get_dashboard_config(), client_id_provider=lambda: "cid").fetch()
    req = sessions.calls.last.request
    assert req.headers["X-Plex-Token"] == "ptok" and "X-Plex-Token" not in str(req.url)
    assert data["sessions"][0]["transcoding"] is True and data["sessions"][1]["transcoding"] is False
    assert data["libraries"][0]["count"] == 5
    assert "ptok" not in json.dumps(data)


@respx.mock
async def test_vaultwarden_down():
    respx.get("http://vault:80/alive").mock(return_value=httpx.Response(500))
    respx.get("http://vault:80/api/version").mock(return_value=httpx.Response(200, text='"1.33.2"'))
    data = await VaultwardenIntegration(settings(), get_dashboard_config()).fetch()
    assert data["online"] is False and data["version"] == "1.33.2"


@respx.mock
async def test_docker_via_proxy():
    items = load_fixture("docker/containers.json")
    inspect = load_fixture("docker/inspect.json")
    respx.get("http://socket-proxy:2375/containers/json").mock(return_value=httpx.Response(200, json=items))
    respx.get("http://socket-proxy:2375/info").mock(return_value=httpx.Response(200, json=load_fixture("docker/info.json")))
    respx.get(url__regex=r"http://socket-proxy:2375/containers/[0-9a-f]+/json").mock(
        side_effect=lambda r: httpx.Response(200, json=inspect[r.url.path.split("/")[2]])
    )
    integration = DockerIntegration(settings(), get_dashboard_config())
    data = await integration.fetch()
    assert data["summary"]["running"] == 7 and data["summary"]["unhealthy"] == 1
    names = [c["display_name"] for g in data["groups"] for c in g["containers"]]
    assert "build-helper" not in names and "pihole" in names
    # restart count increase shows up on the next pass
    bumped = copy.deepcopy(inspect)
    bumped[items[8]["Id"]]["RestartCount"] = 15
    integration._inspect_cache.clear()
    respx.get(url__regex=r"http://socket-proxy:2375/containers/[0-9a-f]+/json").mock(
        side_effect=lambda r: httpx.Response(200, json=bumped[r.url.path.split("/")[2]])
    )
    data = await integration.fetch()
    watchtower = next(c for g in data["groups"] for c in g["containers"] if c["name"] == "watchtower")
    assert watchtower["restart_count"] == 15 and watchtower["restart_increased"] is True


@respx.mock
async def test_anonymous_403_is_not_a_token_rejection():
    """docker-socket-proxy answers 403 for a locked down endpoint; no credentials were sent so it is a plain HTTP error."""
    items = load_fixture("docker/containers.json")
    respx.get("http://socket-proxy:2375/containers/json").mock(return_value=httpx.Response(200, json=items))
    respx.get("http://socket-proxy:2375/info").mock(return_value=httpx.Response(403, text="Forbidden"))
    respx.get(url__regex=r"http://socket-proxy:2375/containers/[0-9a-f]+/json").mock(return_value=httpx.Response(403))
    with pytest.raises(Degraded) as exc:
        await DockerIntegration(settings(), get_dashboard_config()).fetch()
    assert "HTTP 403" in exc.value.message and "token" not in exc.value.message
    assert exc.value.data["summary"]["running"] == 7


@respx.mock
async def test_docker_inspect_refreshes_when_list_state_changes():
    items = copy.deepcopy(load_fixture("docker/containers.json"))
    inspect = load_fixture("docker/inspect.json")
    respx.get("http://socket-proxy:2375/containers/json").mock(side_effect=lambda _r: httpx.Response(200, json=items))
    respx.get("http://socket-proxy:2375/info").mock(return_value=httpx.Response(200, json=load_fixture("docker/info.json")))
    route = respx.get(url__regex=r"http://socket-proxy:2375/containers/[0-9a-f]+/json").mock(
        side_effect=lambda r: httpx.Response(200, json=inspect[r.url.path.split("/")[2]])
    )
    integration = DockerIntegration(settings(), get_dashboard_config())
    await integration.fetch()
    first = route.call_count
    await integration.fetch()
    assert route.call_count == first, "inspect payloads are served from the cache inside the TTL"
    items[0]["State"] = "exited"
    items[0]["Status"] = "Exited (1) 2 seconds ago"
    data = await integration.fetch()
    assert route.call_count == first + 1, "only the container whose state changed is inspected again"
    changed = next(c for g in data["groups"] for c in g["containers"] if c["id"] == items[0]["Id"])
    assert changed["state"] == "exited"


@respx.mock
async def test_firefly_page_cap_is_reported_as_degraded(monkeypatch):
    from app.integrations import firefly as ff

    monkeypatch.setattr(ff, "MAX_PAGES", 2)
    fx = load_fixture("firefly/firefly.json")
    group = fx["transactions"]["data"][0]
    empty = {"data": [], "meta": {"pagination": {"total_pages": 1}}}
    respx.get("http://firefly:8080/api/v1/about").mock(return_value=httpx.Response(200, json=fx["about"]))
    respx.get("http://firefly:8080/api/v1/accounts").mock(return_value=httpx.Response(200, json=empty))
    respx.get("http://firefly:8080/api/v1/transactions").mock(
        side_effect=lambda r: httpx.Response(200, json={"data": [group], "meta": {"pagination": {"total_pages": 5, "current_page": int(r.url.params["page"])}}})
    )
    respx.get("http://firefly:8080/api/v1/summary/basic").mock(return_value=httpx.Response(200, json=fx["summary"]))
    respx.get(url__regex=r"http://firefly:8080/api/v1/insight/.*").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://firefly:8080/api/v1/budgets").mock(return_value=httpx.Response(200, json=empty))
    respx.get("http://firefly:8080/api/v1/bills").mock(return_value=httpx.Response(200, json=empty))
    with pytest.raises(Degraded) as exc:
        await FireflyIntegration(settings(), get_dashboard_config()).fetch()
    assert "truncated at 2 pages" in exc.value.message
    assert len(exc.value.data["transactions"]) == 2 * len(group["attributes"]["transactions"])


def test_firefly_bad_amount_does_not_fail_the_refresh():
    from app.integrations.firefly import flatten_transactions, normalize_accounts

    rows = flatten_transactions([{"id": 1, "attributes": {"transactions": [{"transaction_journal_id": 9, "amount": "n/a", "date": "2026-01-02"}]}}])
    assert rows[0]["amount"] == "0.00"
    accounts = normalize_accounts([{"id": 3, "attributes": {"name": "x", "current_balance": None}}])
    assert accounts[0]["balance"] == "0.00"


@respx.mock
async def test_plex_rails_with_errors_are_not_cached():
    respx.get("http://plex:32400/identity").mock(return_value=httpx.Response(200, json=load_fixture("plex/identity.json")))
    respx.get("http://plex:32400/status/sessions").mock(return_value=httpx.Response(200, json=load_fixture("plex/sessions.json")))
    respx.get("http://plex:32400/library/recentlyAdded").mock(return_value=httpx.Response(200, json=load_fixture("plex/recently_added.json")))
    on_deck = respx.get("http://plex:32400/library/onDeck").mock(return_value=httpx.Response(500))
    respx.get("http://plex:32400/library/sections").mock(return_value=httpx.Response(200, json=load_fixture("plex/sections.json")))
    respx.get(url__regex=r"http://plex:32400/library/sections/\d+/all").mock(return_value=httpx.Response(200, json={"MediaContainer": {"totalSize": 5}}))
    integration = PlexIntegration(settings(), get_dashboard_config(), client_id_provider=lambda: "cid")
    with pytest.raises(Degraded):
        await integration.fetch()
    on_deck.mock(return_value=httpx.Response(200, json=load_fixture("plex/on_deck.json")))
    data = await integration.fetch()
    assert data["on_deck"], "the failed rail is retried on the next refresh instead of staying degraded for RAILS_TTL"
    assert integration._rails is not None
    calls = on_deck.call_count
    await integration.fetch()
    assert on_deck.call_count == calls, "a clean rails result is cached"


@respx.mock
async def test_vaultwarden_backup_status_is_cached(tmp_path):
    (tmp_path / "db.sqlite3").write_text("x")
    respx.get("http://vault:80/alive").mock(return_value=httpx.Response(200))
    respx.get("http://vault:80/api/version").mock(return_value=httpx.Response(200, text='"1.33.2"'))
    integration = VaultwardenIntegration(settings(vaultwarden_backup_dir=str(tmp_path)), get_dashboard_config())
    data = await integration.fetch()
    assert data["backup"]["newest_file"] == "db.sqlite3" and data["backup"]["age_hours"] == 0.0
    (tmp_path / "newer.sqlite3").write_text("y")
    assert (await integration.fetch())["backup"]["newest_file"] == "db.sqlite3", "the directory is rescanned at most every BACKUP_TTL"
    integration._backup = None
    assert (await integration.fetch())["backup"]["newest_file"] == "newer.sqlite3"


@respx.mock
async def test_vaultwarden_can_accept_a_self_signed_certificate(monkeypatch):
    """VAULTWARDEN_VERIFY_TLS=false reaches the card's client and the probe for that one address, nothing else."""
    from app.integrations import probes as probes_mod
    from app.integrations import vaultwarden as vault_mod

    seen: list[bool] = []
    real = vault_mod.make_client

    def spy(*args, **kwargs):
        seen.append(kwargs.get("verify", True))
        return real(*args, **kwargs)

    monkeypatch.setattr(vault_mod, "make_client", spy)
    respx.get("https://vault.lan:8222/alive").mock(return_value=httpx.Response(200))
    respx.get("https://vault.lan:8222/api/version").mock(return_value=httpx.Response(200, text='"1.33.2"'))
    cfg = settings(vaultwarden_url="https://vault.lan:8222", vaultwarden_verify_tls=False)
    data = await VaultwardenIntegration(cfg, get_dashboard_config()).fetch()
    assert data["online"] is True and seen == [False]
    targets = {t["name"]: t["verify"] for t in probes_mod.ProbesIntegration(cfg, get_dashboard_config())._targets()}
    assert targets["Vaultwarden"] is False and targets["Firefly III"] is True
