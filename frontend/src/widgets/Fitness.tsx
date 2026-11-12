import { Activity } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useFitness } from "../api/hooks";
import type { FitnessData } from "../api/types";
import { Card } from "../components/Card";
import { muscleTitle, weightSummary, zoneClass } from "../lib/fitness";

function Row({ to, label, children }: { to: string; label: string; children: ReactNode }) {
  return (
    <li>
      <Link to={to} className="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 hover:bg-ink-800/60">
        <span className="text-xs text-ink-400">{label}</span>
        <span className="flex min-w-0 items-center gap-1.5 text-right text-sm text-ink-200">{children}</span>
      </Link>
    </li>
  );
}

export function FitnessBody({ data }: { data: FitnessData }) {
  const w = data.weight;
  const toneClass = w.rate?.band === "in" ? "text-ink-200" : w.rate?.band === "above" ? "text-red-300" : w.rate ? "text-amber-300" : "text-ink-400";
  return (
    <ul className="-mx-2 space-y-0.5">
      <Row to="/fitness/weight" label="Trend weight">
        <span className={`tabular truncate ${toneClass}`}>{weightSummary(w)}</span>
      </Row>
      <Row to="/fitness/consistency" label="Sessions this week">
        <span className="tabular">
          {data.consistency.this_week} / {data.consistency.target}
        </span>
      </Row>
      <Row to="/fitness/volume" label="Muscle volume">
        <span className="flex items-end gap-0.5" aria-label="Weekly sets per muscle">
          {data.volume.muscles.map((m) => (
            <span
              key={m.muscle}
              title={muscleTitle(m)}
              className={`block w-2 rounded-sm ${zoneClass(m.zone)}`}
              style={{ height: `${Math.max(4, Math.min(16, m.sets * 0.8))}px` }}
            />
          ))}
        </span>
      </Row>
      <Row to="/fitness/strength" label="PRs this week">
        <span className="tabular">{data.strength.prs_this_week}</span>
      </Row>
      {data.stalled.count > 0 && (
        <Row to="/fitness/stalled" label="Stalled lifts">
          <span className="tabular text-amber-300">{data.stalled.count}</span>
        </Row>
      )}
    </ul>
  );
}

export function FitnessWidget() {
  const q = useFitness();
  return (
    <Card title="Fitness" icon={<Activity size={14} />} envelope={q.data} error={q.error} onRetry={() => q.refetch()}>
      {(d) => <FitnessBody data={d} />}
    </Card>
  );
}
