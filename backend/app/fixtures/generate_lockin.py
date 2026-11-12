"""Generate the Lock-In fixtures (anchored on 2026-10-25, a Sunday). Run: python -m app.fixtures.generate_lockin"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ANCHOR = date(2026, 10, 25)
ROTATION = ["pushA", "pullA", "legsA", "pushB", "pullB", "legsB"]
NAMES = {"pushA": "Push A", "pullA": "Pull A", "legsA": "Legs A", "pushB": "Push B", "pullB": "Pull B", "legsB": "Legs B"}
# (exercise key, starting load lb, rep range, weekly increment) per template, keys from Lock-In's program
PROGRAM: dict[str, list[tuple[str, float, int, int, float]]] = {
    "pushA": [
        ("incline-db-press", 60, 6, 10, 2.5),
        ("flat-bench", 155, 6, 10, 5),
        ("cable-fly", 30, 10, 15, 2.5),
        ("seated-db-shoulder-press", 45, 8, 12, 2.5),
        ("cable-lateral-raise", 15, 12, 20, 0),
        ("rope-pushdown", 50, 10, 15, 2.5),
        ("overhead-cable-triceps", 40, 10, 15, 2.5),
    ],
    "pullA": [
        ("pullup-or-pulldown", 140, 6, 10, 5),
        ("chest-supported-row", 90, 8, 12, 5),
        ("single-arm-cable-lat-row", 50, 10, 15, 2.5),
        ("reverse-pec-deck", 70, 12, 20, 5),
        ("ez-bar-curl", 60, 8, 12, 0),
        ("hammer-curl", 30, 10, 15, 2.5),
    ],
    "legsA": [
        ("squat-or-hack", 185, 6, 10, 10),
        ("romanian-deadlift", 165, 8, 10, 5),
        ("leg-extension", 110, 10, 15, 5),
        ("seated-leg-curl", 100, 10, 15, 5),
        ("standing-calf-raise", 180, 10, 15, 10),
        ("cable-crunch", 70, 10, 15, 5),
    ],
    "pushB": [
        ("overhead-press", 95, 6, 10, 2.5),
        ("incline-machine-press", 120, 8, 12, 5),
        ("dips", 0, 8, 12, 0),
        ("cable-lateral-raise", 15, 12, 20, 0),
        ("pec-deck", 100, 12, 15, 5),
        ("ez-skull-crusher", 55, 8, 12, 2.5),
        ("single-arm-pushdown", 25, 12, 15, 0),
    ],
    "pullB": [
        ("barbell-or-tbar-row", 135, 6, 10, 5),
        ("neutral-grip-pulldown", 130, 8, 12, 5),
        ("seated-cable-row", 120, 10, 12, 5),
        ("face-pull", 45, 12, 15, 2.5),
        ("incline-db-curl", 25, 10, 12, 0),
        ("preacher-or-cable-curl", 50, 10, 15, 2.5),
    ],
    "legsB": [
        ("leg-press", 320, 10, 15, 20),
        ("bulgarian-split-squat", 35, 8, 12, 2.5),
        ("lying-leg-curl", 90, 8, 12, 5),
        ("hip-thrust-or-back-ext", 185, 10, 12, 10),
        ("leg-extension", 110, 12, 15, 5),
        ("seated-calf-raise", 90, 12, 20, 5),
        ("hanging-leg-raise", 0, 10, 15, 0),
    ],
}
STALLED = {"ez-bar-curl", "incline-db-curl"}


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    rnd = random.Random(11)
    weigh_ins: list[dict[str, Any]] = []
    # 60 days of morning weigh-ins trending from 152.0 up toward 156 with daily noise, a few days skipped
    for i in range(60, -1, -1):
        d = ANCHOR - timedelta(days=i)
        if rnd.random() < 0.12 and i not in (0, 1):
            continue
        base = 152.0 + (60 - i) * (4.0 / 60)
        w = base + math.sin(i / 2.3) * 0.5 + rnd.uniform(-0.6, 0.6)
        weigh_ins.append({"id": f"w-{d.isoformat()}", "date": d.isoformat(), "weightLb": round(w, 1), "updatedAt": 1761000000000 + i, "deleted": False})
    # four weeks of training: 5 or 6 sessions per week following the rotation, this week has 4 so far (Sunday)
    sessions: list[dict[str, Any]] = []
    idx = 0
    for week_back in range(4, -1, -1):
        monday = ANCHOR - timedelta(days=ANCHOR.weekday()) - timedelta(weeks=week_back)
        # this week: Mon, Tue, Thu, Fri done and Sunday still open; past weeks alternate 5 and 6 sessions
        train_days = [0, 1, 3, 4] if week_back == 0 else ([0, 1, 2, 4, 5] if week_back % 2 else [0, 1, 2, 3, 4, 5])
        for dow in train_days:
            d = monday + timedelta(days=dow)
            if d > ANCHOR:
                continue
            key = ROTATION[idx % 6]
            idx += 1
            started = 1761000000000 + len(sessions) * 10000
            sessions.append(
                {
                    "id": f"s-{d.isoformat()}",
                    "date": d.isoformat(),
                    "templateKey": key,
                    "startedAt": started,
                    "completedAt": started + 3600000,
                    "notes": "",
                    "updatedAt": started,
                    "deleted": False,
                }
            )
    # logged sets: every exercise of the session's template, 3 working sets, loads creeping up week over week
    # (two lifts are deliberately flat so the stalled-lifts view has something to show)
    sets: list[dict[str, Any]] = []
    first_week = min(date.fromisoformat(str(s["date"])) for s in sessions)
    for s in sessions:
        week_no = (date.fromisoformat(str(s["date"])) - first_week).days // 7
        for exercise, base_lb, reps_lo, reps_hi, step in PROGRAM[str(s["templateKey"])]:
            flat = exercise in STALLED
            for set_index in range(3):
                load = base_lb if flat else base_lb + step * week_no
                reps = rnd.randint(reps_lo, reps_hi) - set_index
                sets.append(
                    {
                        "id": f"{s['id']}-{exercise}-{set_index}",
                        "sessionId": s["id"],
                        "exerciseKey": exercise,
                        "setIndex": set_index,
                        "weightLb": float(load),
                        "reps": max(1, reps),
                        "updatedAt": int(s["startedAt"]) + set_index,
                        "deleted": False,
                    }
                )
    last = sessions[-1]
    next_key = ROTATION[(ROTATION.index(str(last["templateKey"])) + 1) % 6]
    week_start = (ANCHOR - timedelta(days=ANCHOR.weekday())).isoformat()
    d7 = (ANCHOR - timedelta(days=7)).isoformat()
    d14 = (ANCHOR - timedelta(days=14)).isoformat()
    this_week = [s for s in sessions if str(s["date"]) >= week_start]
    recent = [w["weightLb"] for w in weigh_ins if w["date"] > d7]
    prev = [w["weightLb"] for w in weigh_ins if d14 < w["date"] <= d7]
    avg7 = round(sum(recent) / len(recent), 1)
    avg7_prev = round(sum(prev) / len(prev), 1)
    summary = {
        "_version": "0.2.1",
        "generatedAt": "2026-10-25T12:00:00.000Z",
        "today": ANCHOR.isoformat(),
        "phase": {"key": "rampBack", "name": "Ramp back", "week": 1, "deload": False},
        "daysUntilGoal": (date(2027, 6, 1) - ANCHOR).days,
        "sessionsThisWeek": len(this_week),
        "sessionsPlannedPerWeek": 6,
        "trainingStreakWeeks": 4,
        "lastSession": {"date": last["date"], "templateKey": last["templateKey"], "templateName": NAMES[last["templateKey"]]},
        "nextSession": {"templateKey": next_key, "templateName": NAMES[next_key]},
        "weight": {
            "latest": {"date": weigh_ins[-1]["date"], "weightLb": weigh_ins[-1]["weightLb"]},
            "avg7": avg7,
            "avg7Prev": avg7_prev,
            "weeklyChangeLb": round(avg7 - avg7_prev, 1),
            "targetWeeklyChangeLb": 0.5,
        },
    }
    export = {"exportedAt": "2026-10-25T12:00:00.000Z", "version": "0.2.1", "weighIns": weigh_ins, "sessions": sessions, "sets": sets}
    return summary, export


if __name__ == "__main__":
    (HERE / "lockin").mkdir(exist_ok=True)
    summary, export = build()
    (HERE / "lockin" / "summary.json").write_text(json.dumps(summary, indent=1))
    (HERE / "lockin" / "export.json").write_text(json.dumps(export, indent=1))
    (HERE / "lockin" / "health.json").write_text(json.dumps({"ok": True, "version": "0.2.1", "builtAt": "2026-10-24T16:30:00.000Z", "auth": "token"}, indent=1))
    print(f"lockin fixtures written: {len(export['weighIns'])} weigh-ins, {len(export['sessions'])} sessions")
