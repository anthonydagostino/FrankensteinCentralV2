import { ArrowDownRight, ArrowUpRight, Dumbbell, ExternalLink, Flame, Minus } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { useTraining } from "../api/hooks";
import type { TrainingData } from "../api/types";
import { Chip } from "../components/Bars";
import { Card } from "../components/Card";
import { formatDateOnly } from "../lib/format";

function signed(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  return n > 0 ? `+${n}` : `${n}`;
}

function WeekSquares({ data, large }: { data: TrainingData; large?: boolean }) {
  if (!data.week) return null;
  return (
    <div className="flex gap-1.5">
      {data.week.map((d) => (
        <div
          key={d.date}
          title={formatDateOnly(d.date, "EEE, MMM d")}
          className={`grid ${large ? "h-10 w-10 text-sm" : "h-8 w-8 text-[11px]"} place-items-center rounded-md border font-semibold ${
            d.done ? "border-accent bg-accent/25 text-accent" : d.future ? "border-ink-700 text-ink-500" : "border-ink-600 bg-ink-800 text-ink-400"
          } ${d.today ? "ring-2 ring-ink-300/40" : ""}`}
        >
          {d.label}
        </div>
      ))}
    </div>
  );
}

export function TrainingBody({ data, large }: { data: TrainingData; large?: boolean }) {
  const w = data.weight;
  const change = w.weekly_change;
  const streakTone = data.streak_risk === "safe" ? "good" : data.streak_risk === "at_risk" ? "warn" : data.streak_risk === "lost" ? "bad" : "neutral";
  const series = (data.weight_series ?? []).map((p) => ({ ...p, label: formatDateOnly(p.date) }));
  const min = series.length ? Math.min(...series.map((p) => p.weight)) : 0;
  const max = series.length ? Math.max(...series.map((p) => p.weight)) : 0;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {data.phase.name && (
          <Chip tone="info">
            {data.phase.name}
            {data.phase.week ? `, week ${data.phase.week}` : ""}
          </Chip>
        )}
        {data.phase.deload && <Chip tone="warn">Deload week</Chip>}
        <Chip tone={streakTone}>
          <Flame size={11} /> {data.streak_weeks} week streak
        </Chip>
        <span className="ml-auto text-[11px] text-ink-400">
          <span className="tabular text-ink-200">{data.days_until_goal}</span> days to {formatDateOnly(data.goal_date, "MMM d")}
        </span>
      </div>

      <div className="rounded-lg bg-ink-800/60 p-3">
        <div className="text-[11px] uppercase tracking-wide text-ink-400">{data.trained_today ? "Done today" : "Next up"}</div>
        <div className={`${large ? "text-2xl" : "text-xl"} font-semibold text-ink-200`}>{data.trained_today ? data.last_session?.name : data.next_session?.name ?? "Rest"}</div>
        <div className="mt-1 text-xs text-ink-400">
          {data.last_session ? `Last: ${data.last_session.name} on ${formatDateOnly(data.last_session.date, "EEE, MMM d")}` : "No sessions logged yet"}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <WeekSquares data={data} large={large} />
        <div className="text-right text-xs text-ink-400">
          <span className="tabular text-base font-semibold text-ink-200">{data.sessions_this_week}</span> of {data.sessions_planned} sessions
          {data.streak_risk === "at_risk" && <div className="text-amber-300">{data.sessions_needed_for_streak} more to keep the streak</div>}
          {data.streak_risk === "lost" && data.streak_weeks > 0 && <div className="text-red-300">Streak ends this week</div>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded-lg bg-ink-800/40 p-2">
          <div className="text-ink-400">Weight</div>
          <div className="tabular text-base font-semibold text-ink-200">{w.latest ? `${w.latest.lb} lb` : "--"}</div>
          <div className="text-[10px] text-ink-500">{w.latest ? (data.weighed_today ? "today" : formatDateOnly(w.latest.date)) : "no weigh-in"}</div>
        </div>
        <div className="rounded-lg bg-ink-800/40 p-2">
          <div className="text-ink-400">7 day avg</div>
          <div className="tabular text-base font-semibold text-ink-200">{w.avg7 !== null ? `${w.avg7} lb` : "--"}</div>
        </div>
        <div className="rounded-lg bg-ink-800/40 p-2">
          <div className="text-ink-400">Weekly change</div>
          <div className={`tabular inline-flex items-center gap-0.5 text-base font-semibold ${w.on_track === false ? "text-amber-300" : "text-ink-200"}`}>
            {change === null ? <Minus size={12} /> : change > 0 ? <ArrowUpRight size={14} /> : change < 0 ? <ArrowDownRight size={14} /> : <Minus size={12} />}
            {change !== null ? `${signed(change)} lb` : "--"}
          </div>
          <div className="text-[10px] text-ink-500">target {signed(w.target_weekly_change)} lb/wk</div>
        </div>
      </div>

      {series.length > 2 && (
        <div className="h-16">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="weight" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#60a5fa" stopOpacity={0} />
                </linearGradient>
              </defs>
              <YAxis hide domain={[Math.floor(min - 1), Math.ceil(max + 1)]} />
              <Tooltip contentStyle={{ background: "#171e1a", border: "1px solid #2f3a33", fontSize: 12 }} labelFormatter={(_, p) => (p && p[0] ? String((p[0].payload as { label: string }).label) : "")} formatter={(v: number) => [`${v} lb`, "Weight"]} />
              <Area type="monotone" dataKey="weight" stroke="#60a5fa" fill="url(#weight)" strokeWidth={1.5} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {data.public_url && (
        <a href={data.public_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md bg-accent/15 px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent/25">
          <Dumbbell size={14} /> Open Lock-In <ExternalLink size={12} />
        </a>
      )}
    </div>
  );
}

export function TrainingWidget({ kiosk }: { kiosk?: boolean }) {
  const q = useTraining();
  return (
    <Card title="Lock-In" icon={<Dumbbell size={14} />} envelope={q.data} error={q.error} onRetry={() => q.refetch()} kiosk={kiosk} actions={q.data?.data?.version ? <span className="text-[11px] text-ink-400">v{q.data.data.version}</span> : null}>
      {(d) => <TrainingBody data={d} large={kiosk} />}
    </Card>
  );
}
