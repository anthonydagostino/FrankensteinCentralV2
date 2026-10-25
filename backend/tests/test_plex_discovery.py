from __future__ import annotations

import httpx
import pytest
import respx

from app.config_loader import get_dashboard_config
from app.integrations.base import TokenRejected, load_fixture
from app.integrations.plex import PlexIntegration, ordered_connections, pick_server
from app.settings import Settings


def settings(**overrides) -> Settings:
    base = dict(mock_mode=False, plex_url="", plex_token="acct-token")
    base.update(overrides)
    return Settings(_env_file=None, **base)


SHARED = {
    "name": "Absolute Cinema",
    "provides": "server",
    "owned": False,
    "presence": True,
    "sourceTitle": "eddiedlugosz",
    "clientIdentifier": "1ada8514308c7dc0e34be30172104c130d2a6c87",
    "accessToken": "server-token",
    "connections": [
        {"protocol": "https", "address": "192.168.4.20", "port": 32400, "uri": "https://192-168-4-20.1ada.plex.direct:32400", "local": True, "relay": False},
        {"protocol": "https", "address": "73.1.2.3", "port": 12345, "uri": "https://73-1-2-3.1ada.plex.direct:12345", "local": False, "relay": False},
        {"protocol": "https", "address": "relay.plex.direct", "port": 8443, "uri": "https://1ada.relay.plex.direct:8443", "local": False, "relay": True},
    ],
}
OWNED = {"name": "Mine", "provides": "server", "owned": True, "presence": False, "clientIdentifier": "own", "accessToken": "own-token", "connections": [{"protocol": "http", "address": "10.0.0.5", "port": 32400, "uri": "http://10.0.0.5:32400", "local": True, "relay": False}]}
PLAYER = {"name": "Living Room", "provides": "player", "connections": []}


def test_pick_server_prefers_name_then_owned_then_present():
    assert pick_server([PLAYER, SHARED, OWNED])["name"] == "Mine"
    assert pick_server([PLAYER, SHARED, OWNED], "absolute cinema")["name"] == "Absolute Cinema"
    assert pick_server([PLAYER, SHARED])["name"] == "Absolute Cinema"
    assert pick_server([PLAYER]) is None


def test_connection_order_public_then_local_then_relay():
    urls = ordered_connections(SHARED)
    assert urls[0] == "https://73-1-2-3.1ada.plex.direct:12345"
    assert urls[1] == "https://73.1.2.3:12345"
    assert urls[-1] == "https://1ada.relay.plex.direct:8443"
    assert "https://192-168-4-20.1ada.plex.direct:32400" in urls


def _mock_server(base: str):
    identity = respx.get(f"{base}/identity").mock(return_value=httpx.Response(200, json=load_fixture("plex/identity.json")))
    respx.get(f"{base}/status/sessions").mock(return_value=httpx.Response(200, json=load_fixture("plex/sessions.json")))
    respx.get(f"{base}/library/recentlyAdded").mock(return_value=httpx.Response(200, json=load_fixture("plex/recently_added.json")))
    respx.get(f"{base}/library/onDeck").mock(return_value=httpx.Response(200, json=load_fixture("plex/on_deck.json")))
    respx.get(f"{base}/library/sections").mock(return_value=httpx.Response(200, json=load_fixture("plex/sections.json")))
    respx.get(url__regex=rf"{base}/library/sections/\d+/all").mock(return_value=httpx.Response(200, json={"MediaContainer": {"totalSize": 7}}))
    return identity


@respx.mock
async def test_discovers_shared_server_and_uses_its_access_token():
    resources = respx.get("https://plex.tv/api/v2/resources").mock(return_value=httpx.Response(200, json=[PLAYER, SHARED]))
    # the public plex.direct address fails, the raw public address works
    respx.get("https://73-1-2-3.1ada.plex.direct:12345/identity").mock(side_effect=httpx.ConnectError("dns"))
    base = "https://73.1.2.3:12345"
    identity = _mock_server(base)
    integration = PlexIntegration(settings(), get_dashboard_config(), client_id_provider=lambda: "cid")
    data = await integration.fetch()
    assert resources.calls.last.request.headers["X-Plex-Token"] == "acct-token"
    assert identity.calls.last.request.headers["X-Plex-Token"] == "server-token"
    assert data["server"]["shared_by"] == "eddiedlugosz" and data["server"]["owned"] is False and data["server"]["via"] == "direct"
    assert data["libraries"][0]["count"] == 7
    assert integration.base_url() == base and integration.headers()["X-Plex-Token"] == "server-token"
    # second fetch reuses the discovery
    await integration.fetch()
    assert resources.call_count == 1


@respx.mock
async def test_falls_back_to_relay_and_rediscovers_after_failure():
    respx.get("https://plex.tv/api/v2/resources").mock(return_value=httpx.Response(200, json=[SHARED]))
    for dead in ("https://73-1-2-3.1ada.plex.direct:12345", "https://73.1.2.3:12345", "https://192-168-4-20.1ada.plex.direct:32400", "https://192.168.4.20:32400"):
        respx.get(f"{dead}/identity").mock(side_effect=httpx.ConnectError("no route"))
    relay = "https://1ada.relay.plex.direct:8443"
    _mock_server(relay)
    integration = PlexIntegration(settings(), get_dashboard_config(), client_id_provider=lambda: "cid")
    data = await integration.fetch()
    assert data["server"]["via"] == "relay"
    # the relay dies later: the cached connection is dropped so the next pass rediscovers
    respx.get(f"{relay}/identity").mock(side_effect=httpx.ConnectError("gone"))
    with pytest.raises(Exception):
        await integration.fetch()
    assert integration.base_url() is None


@respx.mock
async def test_no_server_visible_is_a_clear_error():
    respx.get("https://plex.tv/api/v2/resources").mock(return_value=httpx.Response(200, json=[PLAYER]))
    with pytest.raises(RuntimeError) as exc:
        await PlexIntegration(settings(), get_dashboard_config(), client_id_provider=lambda: "cid").fetch()
    assert "no server" in str(exc.value)


@respx.mock
async def test_bad_account_token():
    respx.get("https://plex.tv/api/v2/resources").mock(return_value=httpx.Response(401, json={"errors": [{"message": "Unauthorized"}]}))
    with pytest.raises(TokenRejected):
        await PlexIntegration(settings(), get_dashboard_config(), client_id_provider=lambda: "cid").fetch()


def test_plex_url_bypasses_discovery():
    integration = PlexIntegration(settings(plex_url="http://10.0.0.5:32400/"), get_dashboard_config(), client_id_provider=lambda: "cid")
    assert integration.base_url() == "http://10.0.0.5:32400" and integration.headers()["X-Plex-Token"] == "acct-token"
    assert integration.is_configured()
    assert not PlexIntegration(settings(plex_token=""), get_dashboard_config()).is_configured()
