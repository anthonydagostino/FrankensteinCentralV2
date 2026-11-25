"""NJ Transit rail departures: parsing, direction logic, the token lifecycle, and the mock board."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.config_loader import get_dashboard_config
from app.integrations.njtransit import BASE_URL, NJTransitIntegration, TokenLimit, classify_status, direction_rows, parse_njt_time
from app.settings import Settings

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 25, 7, 0, tzinfo=NY)
UNION = {"code": "UV", "name": "Union"}
PENN = {"code": "NY", "name": "New York Penn Station"}
NEWARK = {"code": "NP", "name": "Newark Penn Station"}


def settings(tmp_path, **overrides) -> Settings:
    base = dict(mock_mode=False, njt_username="dev@example.com", njt_password="hunter2-hunter2", data_dir=tmp_path)
    base.update(overrides)
    return Settings(_env_file=None, **base)


def stamp(minutes: int) -> str:
    return (NOW + timedelta(minutes=minutes)).strftime("%d-%b-%Y %I:%M:%S %p")


def train(
    train_id: str, minutes: int, stops: list[dict], *, status: str = "ON TIME", late: int = 0, dest: str = "New York Penn Station", track: str = "2"
) -> dict:
    return {
        "TRAIN_ID": train_id,
        "LINE": "Raritan Valley Line",
        "LINEABBREVIATION": "RVL",
        "DESTINATION": dest,
        "SCHED_DEP_DATE": stamp(minutes),
        "SEC_LATE": str(late),
        "STATUS": status,
        "TRACK": track,
        "STOPS": stops,
    }


ROUTE_DIRECT = [
    {"STATION_2CHAR": "RA", "STATIONNAME": "Raritan"},
    {"STATION_2CHAR": "UV", "STATIONNAME": "Union"},
    {"STATION_2CHAR": "NP"},
    {"STATION_2CHAR": "NY"},
]
ROUTE_NEWARK = [{"STATION_2CHAR": "UV"}, {"STATION_2CHAR": "NP"}]
ROUTE_WEST = [{"STATION_2CHAR": "NY"}, {"STATION_2CHAR": "NP"}, {"STATION_2CHAR": "UV"}, {"STATION_2CHAR": "RA"}]


def test_parses_the_api_time_formats():
    assert parse_njt_time("25-Nov-2026 07:12:00 AM", NY) == datetime(2026, 11, 25, 7, 12, tzinfo=NY)
    assert parse_njt_time("11/25/2026 05:30:00 PM", NY) == datetime(2026, 11, 25, 17, 30, tzinfo=NY)
    assert parse_njt_time("2026-11-25T07:12:00", NY) == datetime(2026, 11, 25, 7, 12, tzinfo=NY)
    assert parse_njt_time("soon", NY) is None
    assert parse_njt_time(None, NY) is None


def test_status_classification():
    assert classify_status("ON TIME", 0) == "on_time"
    assert classify_status("in 3 Min", 2) == "on_time"
    assert classify_status("ON TIME", 4) == "delayed"
    assert classify_status("Delayed", 0) == "delayed"
    assert classify_status("BOARDING", 0) == "boarding"
    assert classify_status("All Aboard", 0) == "boarding"
    assert classify_status("CANCELLED", 0) == "cancelled"
    assert classify_status("DEPARTED", 0) == "departed"


def test_direction_rows_keep_only_trains_that_reach_the_destination():
    items = [
        train("5422", 40, ROUTE_DIRECT),
        train("5420", 20, ROUTE_NEWARK, dest="Newark Penn Station", late=360),
        train("5491", 10, ROUTE_WEST, dest="Raritan"),  # already past Newark and New York: going the other way
        train("5418", -10, ROUTE_DIRECT, status="DEPARTED"),
        train("5416", -30, ROUTE_DIRECT),  # scheduled half an hour ago with no delay: gone
        train("5430", 60, ROUTE_DIRECT, status="CANCELLED"),
    ]
    rows = direction_rows(items, UNION, PENN, NEWARK, NOW, NY)
    assert [r["train_id"] for r in rows] == ["5420", "5422", "5430"]
    via = rows[0]
    assert via["direct"] is False and via["via"] == "Newark Penn Station" and via["delay_min"] == 6 and via["state"] == "delayed"
    assert via["scheduled"] == (NOW + timedelta(minutes=20)).isoformat() and via["departs"] == (NOW + timedelta(minutes=26)).isoformat()
    assert rows[1]["direct"] is True and rows[1]["via"] is None and rows[1]["state"] == "on_time" and rows[1]["track"] == "2"
    assert rows[2]["state"] == "cancelled"


def test_direction_rows_without_a_transfer_station_only_lists_direct_trains():
    items = [train("5422", 40, ROUTE_DIRECT), train("5420", 20, ROUTE_NEWARK, dest="Newark Penn Station")]
    assert [r["train_id"] for r in direction_rows(items, UNION, PENN, None, NOW, NY)] == ["5422"]


def test_direction_rows_cap_the_list_and_sort_by_actual_departure():
    items = [train(str(i), 100 - i * 10, ROUTE_DIRECT) for i in range(9)]
    rows = direction_rows(items, UNION, PENN, NEWARK, NOW, NY)
    assert len(rows) == 6
    assert [r["train_id"] for r in rows] == ["8", "7", "6", "5", "4", "3"]


def mock_api(token_calls: list[int], token: str = "tok-1", stations: list[dict] | None = None):  # noqa: S107 - a fake API token
    stations = stations or [
        {"STATION_2CHAR": "UV", "STATIONNAME": "Union"},
        {"STATION_2CHAR": "NY", "STATIONNAME": "New York Penn Station"},
        {"STATION_2CHAR": "NP", "STATIONNAME": "Newark Penn Station"},
    ]

    def get_token(request):
        token_calls.append(1)
        assert not request.url.query, "credentials go in the body, never the query string"
        body = request.content.decode()
        assert "username=dev%40example.com" in body and "password=hunter2-hunter2" in body
        return httpx.Response(200, json={"Authenticated": "True", "UserToken": token})

    def need_token(fn):
        def handler(request):
            body = request.content.decode()
            if f"token={token}" not in body:
                return httpx.Response(500, json={"errorMessage": "Invalid token."})
            return fn(request)

        return handler

    def schedule(request):
        body = request.content.decode()
        if "station=UV" in body:
            items = [train("5418", 9, ROUTE_DIRECT), train("5420", 31, ROUTE_NEWARK, dest="Newark Penn Station")]
            return httpx.Response(
                200, json={"STATION_2CHAR": "UV", "STATIONNAME": "Union", "STATIONMSGS": [{"MSG_TEXT": "Elevator out of service"}], "ITEMS": items}
            )
        assert "station=NY" in body
        home = [{"STATION_2CHAR": "NY"}, {"STATION_2CHAR": "NP"}, {"STATION_2CHAR": "UV"}, {"STATION_2CHAR": "RA"}]
        nec = [{"STATION_2CHAR": "NY"}, {"STATION_2CHAR": "NP"}, {"STATION_2CHAR": "TR"}]
        return httpx.Response(
            200,
            json={
                "STATION_2CHAR": "NY",
                "STATIONNAME": "New York Penn Station",
                "STATIONMSGS": [],
                "ITEMS": [train("3845", 4, nec, dest="Trenton"), train("5431", 26, home, dest="Raritan")],
            },
        )

    respx.post(f"{BASE_URL}/getToken").mock(side_effect=get_token)
    respx.post(f"{BASE_URL}/getStationList").mock(side_effect=need_token(lambda _r: httpx.Response(200, json=stations)))
    respx.post(f"{BASE_URL}/getTrainSchedule").mock(side_effect=need_token(schedule))


@respx.mock
async def test_fetch_resolves_stations_and_keeps_the_token_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr("app.integrations.njtransit.utcnow", lambda: NOW)
    calls: list[int] = []
    mock_api(calls)
    integration = NJTransitIntegration(settings(tmp_path), get_dashboard_config())
    data = await integration.fetch()
    assert data["from"] == UNION and data["to"] == PENN and data["via"] == NEWARK
    assert [(r["train_id"], r["direct"]) for r in data["outbound"]] == [("5418", True), ("5420", False)]
    assert [(r["train_id"], r["direct"], r["via"]) for r in data["inbound"]] == [("3845", False, "Newark Penn Station"), ("5431", True, None)]
    assert data["messages"] == ["Elevator out of service"]
    saved = json.loads((tmp_path / "njt_token.json").read_text())
    assert saved["token"] == "tok-1" and saved["created"] == ["2026-11-25"]
    await integration.fetch()
    assert len(calls) == 1, "the saved token is reused"


@respx.mock
async def test_fetch_renews_a_rejected_token_once(tmp_path, monkeypatch):
    monkeypatch.setattr("app.integrations.njtransit.utcnow", lambda: NOW)
    calls: list[int] = []
    (tmp_path / "njt_token.json").write_text(json.dumps({"token": "stale", "created": ["2026-11-24"]}))
    mock_api(calls, token="tok-2")
    integration = NJTransitIntegration(settings(tmp_path), get_dashboard_config())
    data = await integration.fetch()
    assert len(calls) == 1 and data["outbound"]
    assert json.loads((tmp_path / "njt_token.json").read_text()) == {"token": "tok-2", "created": ["2026-11-25"]}


@respx.mock
async def test_fetch_stops_at_five_tokens_a_day(tmp_path, monkeypatch):
    monkeypatch.setattr("app.integrations.njtransit.utcnow", lambda: NOW)
    calls: list[int] = []
    (tmp_path / "njt_token.json").write_text(json.dumps({"token": "stale", "created": ["2026-11-25"] * 5}))
    mock_api(calls, token="tok-3")
    integration = NJTransitIntegration(settings(tmp_path), get_dashboard_config())
    with pytest.raises(TokenLimit):
        await integration.fetch()
    assert calls == []


@respx.mock
async def test_fetch_reports_bad_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr("app.integrations.njtransit.utcnow", lambda: NOW)
    respx.post(f"{BASE_URL}/getToken").mock(return_value=httpx.Response(200, json={"Authenticated": "False", "UserToken": ""}))
    integration = NJTransitIntegration(settings(tmp_path), get_dashboard_config())
    with pytest.raises(PermissionError):
        await integration.fetch()


@respx.mock
async def test_station_lookup_accepts_codes_and_prefixes(tmp_path, monkeypatch):
    monkeypatch.setattr("app.integrations.njtransit.utcnow", lambda: NOW)
    mock_api(
        [],
        stations=[
            {"STATION_2CHAR": "UV", "STATIONNAME": "Union"},
            {"STATION_2CHAR": "NY", "STATIONNAME": "New York Penn Station"},
            {"STATION_2CHAR": "NP", "STATIONNAME": "Newark Penn Station"},
        ],
    )
    integration = NJTransitIntegration(settings(tmp_path, njt_from="uv", njt_to="new york", njt_via=""), get_dashboard_config())
    data = await integration.fetch()
    assert data["from"] == UNION and data["to"] == PENN and data["via"] is None
    assert [r["train_id"] for r in data["outbound"]] == ["5418"]


@respx.mock
async def test_unknown_station_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.integrations.njtransit.utcnow", lambda: NOW)
    mock_api([])
    integration = NJTransitIntegration(settings(tmp_path, njt_from="Atlantis"), get_dashboard_config())
    with pytest.raises(ValueError, match="Atlantis"):
        await integration.fetch()


def test_mock_board_is_ahead_of_now_and_mixes_direct_and_transfer(tmp_path):
    integration = NJTransitIntegration(Settings(_env_file=None, mock_mode=True, data_dir=tmp_path), get_dashboard_config())
    data = integration.mock()
    assert data["from"]["name"] == "Union" and data["to"]["name"] == "New York Penn Station"
    now = datetime.now(NY)
    for direction in ("outbound", "inbound"):
        rows = data[direction]
        assert 1 <= len(rows) <= 6
        assert all(datetime.fromisoformat(r["departs"]) > now - timedelta(minutes=1) for r in rows)
        assert {r["direct"] for r in rows} == {True, False}
        assert all(r["via"] == ("Newark Penn Station" if not r["direct"] else None) for r in rows)
    assert any(r["state"] == "delayed" for r in data["outbound"])
    assert {r["state"] for r in data["inbound"]} >= {"boarding", "cancelled"}
