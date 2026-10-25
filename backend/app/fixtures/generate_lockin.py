"""Generate the Lock-In fixtures (anchored on 2026-10-25, a Sunday). Run: python -m app.fixtures.generate_lockin"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANCHOR = date(2026, 10, 25)
ROTATION = ["pushA", "pullA", "legsA", "pushB", "pullB", "legsB"]
NAMES = {"pushA": "Push A", "pullA": "Pull A", "legsA": "Legs A", "pushB": "Push B", "pullB": "Pull B", "legsB": "Legs B"}


def build() -> tuple[dict, dict]:
    rnd = random.Random(11)
    weigh_ins = []
    # 60 days of morning weigh-ins trending from 152.0 up toward 156 with daily noise, a few days skipped
    for i in range(60, -1, -1):
        d = ANCHOR - timedelta(days=i)
        if rnd.random() < 0.12 and i not in (0, 1):
            continue
        base = 152.0 + (60 - i) * (4.0 / 60)
        w = base + math.sin(i / 2.3) * 0.5 + rnd.uniform(-0.6, 0.6)
        weigh_ins.append({"id": f"w-{d.isoformat()}", "date": d.isoformat(), "weightLb": round(w, 1), "updatedAt": 1761000000000 + i, "deleted": False})
    # four weeks of training: 5 or 6 sessions per week following the rotation, this week has 4 so far (Sunday)
    sessions = []
    idx = 0
    for week_back in range(4, -1, -1):
        monday = ANCHOR - timedelta(days=ANCHOR.weekday()) - timedelta(weeks=week_back)
        if week_back == 0:
            train_days = [0, 1, 3, 4]  # Mon, Tue, Thu, Fri done; Sunday still open
        else:
            train_days = [0, 1, 2, 4, 5] if week_back % 2 else [0, 1, 2, 3, 4, 5]
        for dow in train_days:
            d = monday + timedelta(days=dow)
            if d > ANCHOR:
                continue
            key = ROTATION[idx % 6]
            idx += 1
            started = 1761000000000 + len(sessions) * 10000
            sessions.append({"id": f"s-{d.isoformat()}", "date": d.isoformat(), "templateKey": key, "startedAt": started, "completedAt": started + 3600000, "notes": "", "updatedAt": started, "deleted": False})
    last = sessions[-1]
    next_key = ROTATION[(ROTATION.index(last["templateKey"]) + 1) % 6]
    this_week = [s for s in sessions if s["date"] >= (ANCHOR - timedelta(days=ANCHOR.weekday())).isoformat()]
    recent = [w["weightLb"] for w in weigh_ins if w["date"] > (ANCHOR - timedelta(days=7)).isoformat()]
    prev = [w["weightLb"] for w in weigh_ins if (ANCHOR - timedelta(days=14)).isoformat() < w["date"] <= (ANCHOR - timedelta(days=7)).isoformat()]
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
        "weight": {"latest": {"date": weigh_ins[-1]["date"], "weightLb": weigh_ins[-1]["weightLb"]}, "avg7": avg7, "avg7Prev": avg7_prev, "weeklyChangeLb": round(avg7 - avg7_prev, 1), "targetWeeklyChangeLb": 0.5},
    }
    export = {"exportedAt": "2026-10-25T12:00:00.000Z", "version": "0.2.1", "weighIns": weigh_ins, "sessions": sessions, "sets": []}
    return summary, export


if __name__ == "__main__":
    (HERE / "lockin").mkdir(exist_ok=True)
    summary, export = build()
    (HERE / "lockin" / "summary.json").write_text(json.dumps(summary, indent=1))
    (HERE / "lockin" / "export.json").write_text(json.dumps(export, indent=1))
    (HERE / "lockin" / "health.json").write_text(json.dumps({"ok": True, "version": "0.2.1", "builtAt": "2026-10-24T16:30:00.000Z", "auth": "token"}, indent=1))
    print(f"lockin fixtures written: {len(export['weighIns'])} weigh-ins, {len(export['sessions'])} sessions")
