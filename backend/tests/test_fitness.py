"""Fitness analytics: the pure calculations and the routes that serve them."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.fitness import calc
from app.services.fitness.build import build_fitness
from app.services.fitness.muscle_map import MUSCLES, load_map, seed_map, validate_entry
from app.services.fitness.settings import FitnessSettings, load_settings, merge_settings

TODAY = date(2026, 10, 25)  # a Sunday
S = FitnessSettings()


def weigh(days: list[int], start: float = 150.0, step: float = 0.1) -> list[dict]:
    """Weigh-ins `days` ago (0 = today) rising `step` per day."""
    return [{"date": (TODAY - timedelta(days=d)).isoformat(), "weightLb": start + step * (60 - d), "deleted": False} for d in days]


def session(day: int, sid: str | None = None, completed: bool = True) -> dict:
    d = TODAY - timedelta(days=day)
    return {"id": sid or f"s{day}", "date": d.isoformat(), "templateKey": "pushA", "completedAt": 1 if completed else None, "deleted": False}


def lift(sid: str, exercise: str, weight: float, reps: int, index: int = 0) -> dict:
    return {"sessionId": sid, "exerciseKey": exercise, "setIndex": index, "weightLb": weight, "reps": reps, "deleted": False}


# ---- trend weight and rate ---------------------------------------------------------------------------------


def test_trend_seeds_with_the_first_weigh_in_and_carries_forward_on_missing_days():
    points = calc.trend_points(weigh([3, 1, 0], start=150, step=0), 0.5, TODAY)
    assert [p[0] for p in points] == [TODAY - timedelta(days=3), TODAY - timedelta(days=2), TODAY - timedelta(days=1), TODAY]
    assert points[0][2] == 150.0 and points[1][1] is None and points[1][2] == 150.0  # the gap carries the trend
    points = calc.trend_points([{"date": "2026-10-23", "weightLb": 150}, {"date": "2026-10-25", "weightLb": 160}], 0.5, TODAY)
    assert points[-1][2] == 155.0  # 150 + 0.5 * (160 - 150)


def test_rate_is_hidden_until_14_weigh_in_days():
    few = weigh(list(range(13)))
    assert calc.weigh_in_days(few) == 13
    out = build_fitness({"weighIns": few, "sessions": [], "sets": []}, TODAY, S, seed_map())
    assert out["weight"]["status"] == "collecting" and out["weight"]["rate"] is None and out["weight"]["days_of_data"] == 13
    assert out["weight"]["trend"] is not None and out["weight"]["corridor"] == []
    enough = weigh(list(range(28)))
    out = build_fitness({"weighIns": enough, "sessions": [], "sets": []}, TODAY, S, seed_map())
    assert out["weight"]["status"] == "ok" and out["weight"]["rate"]["lb_per_week"] > 0


def test_rate_and_band_from_a_steady_gain():
    # 0.05 lb/day raw with alpha 1 (trend == raw) is 0.35 lb/week; at ~150 lb that is about 1.0 %/month
    points = calc.trend_points(weigh(list(range(40)), start=150, step=0.05), 1.0, TODAY)
    rate = calc.rate_of_gain(points, TODAY)
    assert rate is not None and rate["lb_per_week"] == pytest.approx(0.35, abs=0.01)
    assert rate["pct_per_month"] == pytest.approx(0.05 * calc.DAYS_PER_MONTH / points[-1][2] * 100, rel=1e-6)
    assert calc.band_status(0.5, 1.0, 1.5) == "below" and calc.band_status(1.2, 1.0, 1.5) == "in" and calc.band_status(2.0, 1.0, 1.5) == "above"


def test_no_weigh_ins_at_all_is_an_empty_but_valid_payload():
    out = build_fitness({"weighIns": [], "sessions": [], "sets": []}, TODAY, S, seed_map())
    assert out["weight"]["trend"] is None and out["weight"]["series"] == [] and out["bulk_quality"] is None
    assert out["consistency"]["this_week"] == 0 and all(w["sessions"] == 0 for w in out["consistency"]["weeks"])
    assert out["strength"]["exercises"] == [] and out["stalled"]["count"] == 0


# ---- e1RM -------------------------------------------------------------------------------------------------------


def test_epley_rules():
    assert calc.epley(200, 1) == 200  # a single is its own max
    assert calc.epley(200, 5) == pytest.approx(200 * (1 + 5 / 30))
    assert calc.epley(200, 11) is None  # above 10 reps gives no estimate
    assert calc.epley(0, 8) is None  # bodyweight work has no external load
    assert calc.epley(200, 0) is None


def test_session_keeps_the_best_e1rm_per_exercise():
    rows = calc.dated_sets([session(1, "a")], [lift("a", "flat-bench", 185, 5), lift("a", "flat-bench", 200, 2, 1), lift("a", "flat-bench", 135, 15, 2)])
    e = calc.session_e1rms(rows)
    assert list(e) == ["flat-bench"] and len(e["flat-bench"]) == 1
    assert e["flat-bench"][0][1] == pytest.approx(max(185 * (1 + 5 / 30), 200 * (1 + 2 / 30)))


# ---- volume ----------------------------------------------------------------------------------------------------


def test_fractional_sets_and_unmapped_exercises():
    sessions = [session(0, "a")]
    sets = [lift("a", "flat-bench", 185, 8, i) for i in range(3)] + [lift("a", "mystery-machine", 50, 10)]
    rows = calc.dated_sets(sessions, sets)
    week = calc.weekly_sets(rows, seed_map(), calc.week_start(TODAY))
    assert week["muscles"]["chest"] == 3.0 and week["muscles"]["triceps"] == 1.5 and week["muscles"]["shoulders"] == 1.5
    assert week["muscles"]["back"] == 0.0 and week["unmapped"] == {"mystery-machine": 1}
    out = build_fitness({"weighIns": [], "sessions": sessions, "sets": sets}, TODAY, S, seed_map())
    assert out["volume"]["unmapped"] == [{"exercise_key": "mystery-machine", "sets": 1}]
    chest = next(m for m in out["volume"]["muscles"] if m["muscle"] == "chest")
    assert chest["exercises"] == [{"exercise_key": "flat-bench", "name": "Flat bench press", "sets": 3.0}]


def test_zones_follow_the_settings():
    assert calc.zone(3.5, S.zones) == "below_minimum"
    assert calc.zone(4, S.zones) == "building" and calc.zone(9.5, S.zones) == "building"
    assert calc.zone(10, S.zones) == "target" and calc.zone(20, S.zones) == "target"
    assert calc.zone(20.5, S.zones) == "high"


def test_week_with_zero_sessions_and_days_since_muscle():
    sessions = [session(9, "old")]  # last week, nothing this week
    sets = [lift("old", "squat-or-hack", 225, 5)]
    out = build_fitness({"weighIns": [], "sessions": sessions, "sets": sets}, TODAY, S, seed_map())
    assert out["consistency"]["this_week"] == 0
    assert all(m["sets"] == 0.0 and m["zone"] == "below_minimum" for m in out["volume"]["muscles"])
    since = {d["muscle"]: d["days"] for d in out["consistency"]["days_since_muscle"]}
    assert since["quads"] == 9 and since["glutes"] == 9 and since["chest"] is None
    assert out["consistency"]["weeks"][-2]["sessions"] == 1 and len(out["consistency"]["heatmap"]) == 84


def test_incomplete_sessions_do_not_count():
    sessions = [session(0, "a", completed=False)]
    out = build_fitness({"weighIns": [], "sessions": sessions, "sets": [lift("a", "flat-bench", 185, 8)]}, TODAY, S, seed_map())
    assert out["consistency"]["this_week"] == 0 and out["volume"]["muscles"][0]["sets"] == 0.0


# ---- PRs and stalls -------------------------------------------------------------------------------------------


def test_rep_prs_require_beating_both_weight_and_reps():
    sessions = [session(20, "a"), session(10, "b"), session(1, "c")]
    sets = [lift("a", "flat-bench", 185, 5), lift("b", "flat-bench", 185, 5), lift("b", "flat-bench", 175, 8, 1), lift("c", "flat-bench", 190, 5)]
    rows = calc.dated_sets(sessions, sets)
    prs = calc.rep_prs(rows)["flat-bench"]
    assert [(p.weight, p.reps) for p in prs] == [(185, 5), (175, 8), (190, 5)]  # the repeat 185x5 is not a PR
    assert calc.best_reps_per_weight(rows, "flat-bench")[0] == {"weight": 190.0, "reps": 5, "date": (TODAY - timedelta(days=1)).isoformat()}
    out = build_fitness({"weighIns": [], "sessions": sessions, "sets": sets}, TODAY, S, seed_map())
    assert out["strength"]["prs_this_week"] == 2  # 190x5 is a rep PR and a new e1RM best, both dated this week
    assert {p["kind"] for p in out["strength"]["recent_prs"]} == {"rep", "e1rm"}
    assert all(p["date"] != (TODAY - timedelta(days=20)).isoformat() for p in out["strength"]["recent_prs"]), "first session is a baseline"


def test_stall_uses_the_regression_line_and_needs_four_sessions():
    flat = [(TODAY - timedelta(days=d), 200.0 + (1 if d % 2 else -1)) for d in (35, 28, 21, 14, 7, 0)]
    result = calc.stall(flat, TODAY, 6, 1.0)
    assert result is not None and result["stalled"] is True and abs(result["pct_change"]) < 1.0
    rising = [(TODAY - timedelta(days=d), 200.0 + (35 - d)) for d in (35, 28, 21, 14, 7, 0)]
    assert calc.stall(rising, TODAY, 6, 1.0)["stalled"] is False
    assert calc.stall(flat[:3], TODAY, 6, 1.0) is None  # three sessions are not enough
    old = [(TODAY - timedelta(days=d), 200.0) for d in (90, 80, 70, 60)]
    assert calc.stall(old, TODAY, 6, 1.0) is None  # outside the window


def test_bulk_quality_states():
    assert calc.bulk_state(2.0, 5.0) == "on_track"
    assert calc.bulk_state(2.0, 0.5) == "gaining_without_strength"
    assert calc.bulk_state(0.2, 5.0) == "recomping"
    assert calc.bulk_state(0.0, 0.0) == "under_eating" and calc.bulk_state(-1.5, -3.0) == "under_eating"


def test_strength_index_normalizes_each_lift_to_100_and_carries_gaps():
    e1rms = {"flat-bench": [(TODAY - timedelta(weeks=w), 200.0 + (7 - w) * 2) for w in (7, 6, 5, 3, 1, 0)]}
    index = calc.strength_index(e1rms, TODAY, 8)
    assert index is not None and len(index) == 8 and index[0]["strength_index"] == 100.0
    assert index[-1]["strength_index"] == pytest.approx(214 / 200 * 100, abs=0.1)
    assert calc.strength_index({"flat-bench": e1rms["flat-bench"][:3]}, TODAY, 8) is None  # fewer than 4 sessions


# ---- settings and map ------------------------------------------------------------------------------------------


def test_settings_defaults_merge_and_validation():
    assert load_settings(None).alpha == 0.1 and load_settings("not json").target_sessions == 6
    merged = merge_settings(S, {"alpha": 0.2, "zones": {"target_max": 22}})
    assert merged.alpha == 0.2 and merged.zones.target_max == 22 and merged.zones.building_max == 10
    with pytest.raises(ValueError):
        merge_settings(S, {"band_low_pct": 3, "band_high_pct": 1})
    with pytest.raises(ValueError):
        merge_settings(S, {"zones": {"building_max": 30}})


def test_muscle_map_seed_covers_the_program_and_overrides_validate():
    seed = seed_map()
    assert len(seed) == 37 and all(set(e["primary"]) <= set(MUSCLES) for e in seed.values())
    assert seed["flat-bench"] == {"name": "Flat bench press", "primary": ["chest"], "secondary": ["triceps", "shoulders"]}
    merged = load_map('{"flat-bench": {"name": "Bench", "primary": ["chest"], "secondary": []}, "bad": {"primary": ["nope"]}}')
    assert merged["flat-bench"]["secondary"] == [] and "bad" not in merged
    with pytest.raises(ValueError):
        validate_entry("x", {"primary": ["chest"], "secondary": ["chest"]})
    with pytest.raises(ValueError):
        validate_entry("x", {"primary": [], "secondary": []})


# ---- routes ----------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import asyncio

    from app.main import build_state
    from app.settings import get_settings

    state = build_state(get_settings(), db_path=str(tmp_path_factory.mktemp("db") / "fitness.db"))
    app.state.fc = state
    asyncio.run(state.scheduler.refresh_once(state.integrations["lockin"]))
    from app import auth as authlib

    authlib._attempts.clear()  # earlier modules' logins count against the per-IP rate limit
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"password": "x"}).status_code == 200
    return c


def test_fitness_route_is_an_envelope_over_the_lockin_export(client):
    env = client.get("/api/fitness").json()
    assert env["module"] == "fitness" and env["status"] == "ok" and env["data"]["units"] == "lb"
    assert {m["muscle"] for m in env["data"]["volume"]["muscles"]} == set(MUSCLES)
    assert env["data"]["strength"]["exercises"] and env["data"]["weight"]["status"] == "ok"
    lockin = client.get("/api/lockin").json()
    assert "_export" not in lockin["data"], "the raw export never reaches the browser through /api/lockin"


def test_settings_and_map_routes(client):
    assert client.get("/api/fitness/settings").json()["alpha"] == 0.1
    r = client.put("/api/fitness/settings", json={"alpha": 0.25, "target_sessions": 5})
    assert r.status_code == 200 and r.json()["alpha"] == 0.25
    assert client.get("/api/fitness").json()["data"]["settings"]["target_sessions"] == 5
    assert client.put("/api/fitness/settings", json={"alpha": 5}).status_code == 400
    m = client.get("/api/fitness/muscle-map").json()
    assert "flat-bench" in m["map"] and m["muscles"] == MUSCLES and m["unmapped"] == []
    r = client.put(
        "/api/fitness/muscle-map", json={"exercise_key": "landmine-press", "name": "Landmine press", "primary": ["chest"], "secondary": ["shoulders"]}
    )
    assert r.status_code == 200 and r.json()["map"]["landmine-press"]["primary"] == ["chest"]
    assert client.put("/api/fitness/muscle-map", json={"exercise_key": "x", "primary": ["wings"]}).status_code == 400
