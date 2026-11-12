import { ChevronDown } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Navigate, NavLink, useParams } from "react-router-dom";
import {
  Area,
  Bar,
  BarChart,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type DotProps,
} from "recharts";
import { useFitness, useFitnessSettings, useMuscleMap, useSaveFitnessSettings, useSaveMuscleEntry } from "../api/hooks";
import type { FitnessData, FitnessSettings, FitnessZones, Muscle, MuscleMapEntry, StrengthPoint, VolumeMuscle } from "../api/types";
import { Chip } from "../components/Bars";
import { ErrorState, SetupHint, Skeleton } from "../components/Card";
import { SectionLabel } from "../components/SectionLabel";
import { PANEL_CLASS, TOOLTIP_STYLE } from "../lib/ui";
import { formatDateOnly } from "../lib/format";
import {
  bandLabel,
  bandTone,
  bulkTone,
  chunkWeeks,
  COLLECTING_DAYS,
  defaultExerciseKey,
  FITNESS_VIEWS,
  formatSets,
  heatmapClass,
  isFitnessView,
  MUSCLE_COLORS,
  MUSCLES,
  signed,
  titleCase,
  VIEW_COPY,
  VIEW_TITLE,
  volumeScaleMax,
  zoneClass,
  zoneColor,
  zoneLabel,
  zoneTone,
  type FitnessView,
} from "../lib/fitness";

const TICK = { fill: "#97a69c", fontSize: 10 } as const;
const INPUT_CLASS = "mt-1 w-full rounded border border-ink-700 bg-ink-900 px-2 py-1.5 text-sm text-ink-200";
const BUTTON_CLASS = "rounded bg-accent/20 px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent/30 disabled:opacity-50";
const dateTick = (v: unknown) => formatDateOnly(String(v));
const dateLabel = (v: unknown) => formatDateOnly(String(v), "EEE, MMM d");

/** A chevron toggled block; `defaultOpen` picks the first state. */
function Disclosure({ label, defaultOpen = false, children }: { label: ReactNode; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 text-sm text-ink-300 hover:text-ink-200"
      >
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} /> {label}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

/** The collapsible "What this is" and "Why it matters" block at the top of every view. */
function Explainer({ view }: { view: FitnessView }) {
  const copy = VIEW_COPY[view];
  return (
    <section className={`${PANEL_CLASS} p-4`}>
      <Disclosure defaultOpen label={<span className="font-semibold text-ink-200">About {VIEW_TITLE[view].toLowerCase()}</span>}>
        <div className="grid gap-3 text-sm text-ink-300 md:grid-cols-2">
          <div>
            <SectionLabel>What this is</SectionLabel>
            <p>{copy.what}</p>
          </div>
          <div>
            <SectionLabel>Why it matters</SectionLabel>
            <p>{copy.why}</p>
          </div>
        </div>
      </Disclosure>
    </section>
  );
}

function Stat({ label, value, sub, children }: { label: string; value: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="rounded-lg bg-ink-800/40 p-2 text-xs">
      <div className="text-ink-400">{label}</div>
      <div className="tabular flex flex-wrap items-center gap-2 text-base font-semibold text-ink-200">
        {value}
        {children}
      </div>
      {sub && <div className="text-[10px] text-ink-500">{sub}</div>}
    </div>
  );
}

// ---- settings

function NumberField({
  label,
  value,
  step,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  step: number;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  return (
    <label className="block text-xs text-ink-400">
      {label}
      <input type="number" step={step} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={INPUT_CLASS} />
    </label>
  );
}

function SettingsForm({ initial, readOnly }: { initial: FitnessSettings; readOnly: boolean }) {
  const save = useSaveFitnessSettings();
  const [form, setForm] = useState<Record<string, string>>({
    alpha: String(initial.alpha),
    band_low_pct: String(initial.band_low_pct),
    band_high_pct: String(initial.band_high_pct),
    target_sessions: String(initial.target_sessions),
    below_minimum_max: String(initial.zones.below_minimum_max),
    building_max: String(initial.zones.building_max),
    target_max: String(initial.zones.target_max),
    plateau_weeks: String(initial.plateau_weeks),
    flat_pct: String(initial.flat_pct),
  });
  const set = (key: string) => (v: string) => setForm((f) => ({ ...f, [key]: v }));
  const num = (key: string) => Number(form[key]);
  const valid = Object.values(form).every((v) => v.trim() !== "" && !Number.isNaN(Number(v)));
  const fields: [string, string, number][] = [
    ["alpha", "Trend smoothing (alpha)", 0.01],
    ["band_low_pct", "Band low, % per month", 0.1],
    ["band_high_pct", "Band high, % per month", 0.1],
    ["target_sessions", "Target sessions per week", 1],
    ["below_minimum_max", "Below minimum up to (sets)", 1],
    ["building_max", "Building up to (sets)", 1],
    ["target_max", "Target up to (sets)", 1],
    ["plateau_weeks", "Plateau window (weeks)", 1],
    ["flat_pct", "Flat threshold, %", 0.1],
  ];
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        {fields.map(([key, label, step]) => (
          <NumberField key={key} label={label} value={form[key]} step={step} onChange={set(key)} disabled={readOnly} />
        ))}
      </div>
      {save.error && <p className="text-xs text-red-300">{save.error.message}</p>}
      {save.isSuccess && !save.isPending && <p className="text-xs text-accent">Saved</p>}
      <button
        type="button"
        disabled={readOnly || save.isPending || !valid}
        className={BUTTON_CLASS}
        onClick={() =>
          save.mutate({
            alpha: num("alpha"),
            band_low_pct: num("band_low_pct"),
            band_high_pct: num("band_high_pct"),
            target_sessions: num("target_sessions"),
            zones: { below_minimum_max: num("below_minimum_max"), building_max: num("building_max"), target_max: num("target_max") },
            plateau_weeks: num("plateau_weeks"),
            flat_pct: num("flat_pct"),
          })
        }
      >
        Save
      </button>
    </div>
  );
}

/** Loads the stored settings and seeds the form; the effective values from the data route stand in until then. */
function SettingsEditor({ fallback, readOnly }: { fallback: FitnessSettings; readOnly: boolean }) {
  const q = useFitnessSettings();
  const initial = q.data ?? fallback;
  return (
    <div>
      {q.error && <p className="mb-2 text-xs text-amber-300">Showing the effective values, the saved settings could not be loaded: {q.error.message}</p>}
      <SettingsForm key={JSON.stringify(initial)} initial={initial} readOnly={readOnly} />
    </div>
  );
}

// ---- weight

type WeightRow = { date: string; raw?: number | null; trend?: number; band?: [number, number] };

function WeightView({ data, readOnly }: { data: FitnessData; readOnly: boolean }) {
  const w = data.weight;
  const bq = data.bulk_quality;
  const chart = useMemo(() => {
    const byDate = new Map<string, WeightRow>();
    for (const p of w.series) byDate.set(p.date, { date: p.date, raw: p.raw, trend: p.trend });
    for (const c of w.corridor) byDate.set(c.date, { ...(byDate.get(c.date) ?? { date: c.date }), band: [c.low, c.high] });
    const rows = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
    const values = rows.flatMap((r) => [r.raw, r.trend, ...(r.band ?? [])]).filter((v): v is number => typeof v === "number");
    return { rows, min: values.length ? Math.floor(Math.min(...values) - 1) : 0, max: values.length ? Math.ceil(Math.max(...values) + 1) : 1 };
  }, [w.series, w.corridor]);
  const collecting = w.status === "collecting";
  return (
    <>
      <section className={`${PANEL_CLASS} p-4`}>
        <SectionLabel>Trend weight, last 120 days</SectionLabel>
        {collecting && (
          <p className="mb-3 rounded-lg border border-dashed border-ink-600 bg-ink-800/40 p-3 text-sm text-ink-300">
            Collecting data: {w.days_of_data} of {COLLECTING_DAYS} weigh-in days
          </p>
        )}
        {!collecting && (
          <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-4">
            <Stat label="Trend" value={w.trend ? `${w.trend.lb.toFixed(1)} lb` : "--"} sub={w.trend ? formatDateOnly(w.trend.date) : undefined} />
            <Stat
              label="Rate"
              value={w.rate ? `${signed(w.rate.lb_per_week, 2)} lb/wk` : "--"}
              sub={w.rate ? `${signed(w.rate.pct_per_month, 2)} % per month` : undefined}
            >
              {w.rate && <Chip tone={bandTone(w.rate.band)}>{bandLabel(w.rate.band)}</Chip>}
            </Stat>
            <Stat label="30 days" value={w.change_30d_lb !== null ? `${signed(w.change_30d_lb)} lb` : "--"} />
            <Stat label="90 days" value={w.change_90d_lb !== null ? `${signed(w.change_90d_lb)} lb` : "--"} />
          </div>
        )}
        {chart.rows.length === 0 ? (
          <p className="text-sm text-ink-500">No weigh-ins yet</p>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chart.rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                <XAxis dataKey="date" tickFormatter={dateTick} tick={TICK} axisLine={false} tickLine={false} minTickGap={32} />
                <YAxis domain={[chart.min, chart.max]} tick={TICK} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  labelFormatter={dateLabel}
                  formatter={(v: number | [number, number], name: string) => [
                    Array.isArray(v) ? `${v[0].toFixed(1)} to ${v[1].toFixed(1)} lb` : `${Number(v).toFixed(1)} lb`,
                    name,
                  ]}
                />
                <Area
                  dataKey="band"
                  name="Target band"
                  stroke="none"
                  fill="#4ade80"
                  fillOpacity={0.12}
                  connectNulls={false}
                  isAnimationActive={false}
                  legendType="none"
                />
                <Line
                  dataKey="raw"
                  name="Weigh-in"
                  stroke="none"
                  dot={{ r: 2, fill: "#6b7a71", strokeWidth: 0 }}
                  activeDot={{ r: 3 }}
                  isAnimationActive={false}
                />
                <Line dataKey="trend" name="Trend" stroke="#60a5fa" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section className={`${PANEL_CLASS} p-4`}>
        <div className="flex flex-wrap items-center gap-2">
          <SectionLabel className="mb-0">Bulk quality, last 8 weeks</SectionLabel>
          {bq && <Chip tone={bulkTone(bq.state)}>{bq.label}</Chip>}
          {bq && (
            <span className="text-[11px] text-ink-400">
              weight {signed(bq.weight_change_pct)}%, strength {signed(bq.strength_change_pct)}%
            </span>
          )}
        </div>
        {!bq ? (
          <p className="mt-2 text-sm text-ink-500">Not enough data yet</p>
        ) : (
          <div className="mt-2 h-48">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={bq.weeks} margin={{ top: 8, right: -16, bottom: 0, left: -16 }}>
                <XAxis dataKey="week_start" tickFormatter={dateTick} tick={TICK} axisLine={false} tickLine={false} />
                <YAxis yAxisId="lb" domain={["dataMin - 1", "dataMax + 1"]} tick={TICK} axisLine={false} tickLine={false} />
                <YAxis yAxisId="idx" orientation="right" domain={["dataMin - 2", "dataMax + 2"]} tick={TICK} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  labelFormatter={(v) => `Week of ${formatDateOnly(String(v))}`}
                  formatter={(v: number) => Number(v).toFixed(1)}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line yAxisId="lb" dataKey="trend_lb" name="Trend weight (lb)" stroke="#60a5fa" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line yAxisId="idx" dataKey="strength_index" name="Strength index" stroke="#4ade80" strokeWidth={2} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section className={`${PANEL_CLASS} p-4`}>
        <Disclosure label="Settings">
          <SettingsEditor fallback={data.settings} readOnly={readOnly} />
        </Disclosure>
      </section>
    </>
  );
}

// ---- consistency

function ConsistencyView({ data }: { data: FitnessData }) {
  const c = data.consistency;
  const weeks = chunkWeeks(c.heatmap);
  const dayLabels = ["M", "T", "W", "T", "F", "S", "S"];
  return (
    <>
      <section className={`${PANEL_CLASS} p-4`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <SectionLabel>Sessions, last 12 weeks</SectionLabel>
          <span className="text-xs text-ink-400">
            This week <span className="tabular text-ink-200">{c.this_week}</span> of {c.target}
          </span>
        </div>
        <div className="flex gap-1 overflow-x-auto pb-1">
          <div className="grid grid-rows-7 gap-1 pr-1 text-[9px] leading-none text-ink-500">
            {dayLabels.map((d, i) => (
              <span key={i} className="flex h-4 items-center">
                {d}
              </span>
            ))}
          </div>
          {weeks.map((week, i) => (
            <div key={week[0]?.date ?? i} className="grid grid-rows-7 gap-1">
              {week.map((cell) => (
                <span
                  key={cell.date}
                  title={`${formatDateOnly(cell.date, "EEE, MMM d")}: ${cell.sessions} ${cell.sessions === 1 ? "session" : "sessions"}`}
                  className={`block h-4 w-4 rounded-sm ${heatmapClass(cell.sessions)}`}
                />
              ))}
            </div>
          ))}
        </div>
        <div className="mt-4 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={c.weeks} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
              <XAxis dataKey="week_start" tickFormatter={dateTick} tick={TICK} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={TICK} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "#222b26" }} labelFormatter={(v) => `Week of ${formatDateOnly(String(v))}`} />
              <ReferenceLine
                y={c.target}
                stroke="#fbbf24"
                strokeDasharray="4 4"
                label={{ value: `target ${c.target}`, fill: "#fbbf24", fontSize: 10, position: "insideTopRight" }}
              />
              <Bar dataKey="sessions" name="Sessions" fill="#4ade80" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className={`${PANEL_CLASS} p-4`}>
        <SectionLabel>Days since last trained</SectionLabel>
        <ul className="grid grid-cols-2 gap-x-6 sm:grid-cols-5">
          {c.days_since_muscle.map((m) => (
            <li key={m.muscle} className="flex items-center justify-between border-b border-ink-800 py-1 text-sm">
              <span className="text-ink-300">{titleCase(m.muscle)}</span>
              <span className={`tabular ${m.days === null || m.days > 7 ? "text-amber-300" : "text-ink-200"}`}>{m.days === null ? "never" : m.days}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

// ---- volume

function MuscleChecks({
  label,
  selected,
  blocked,
  disabled,
  onToggle,
}: {
  label: string;
  selected: Muscle[];
  blocked: Muscle[];
  disabled: boolean;
  onToggle: (m: Muscle) => void;
}) {
  return (
    <fieldset className="min-w-0">
      <legend className="text-xs text-ink-400">{label}</legend>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
        {MUSCLES.map((m) => (
          <label key={m} className={`inline-flex items-center gap-1 text-xs ${blocked.includes(m) ? "text-ink-500" : "text-ink-200"}`}>
            <input
              type="checkbox"
              className="accent-[#4ade80]"
              checked={selected.includes(m)}
              disabled={disabled || blocked.includes(m)}
              onChange={() => onToggle(m)}
            />{" "}
            {m}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function MuscleEntryEditor({ exerciseKey, initial, readOnly }: { exerciseKey: string; initial?: MuscleMapEntry; readOnly: boolean }) {
  const save = useSaveMuscleEntry();
  const [name, setName] = useState(initial?.name ?? exerciseKey);
  const [primary, setPrimary] = useState<Muscle[]>(initial?.primary ?? []);
  const [secondary, setSecondary] = useState<Muscle[]>(initial?.secondary ?? []);
  const flip = (list: Muscle[], m: Muscle) => (list.includes(m) ? list.filter((x) => x !== m) : [...list, m]);
  return (
    <div className="space-y-2 rounded-lg bg-ink-800/50 p-3">
      <div className="flex flex-wrap items-end gap-3">
        <code className="font-mono text-xs text-ink-400">{exerciseKey}</code>
        <label className="block min-w-[12rem] flex-1 text-xs text-ink-400">
          Name
          <input value={name} disabled={readOnly} onChange={(e) => setName(e.target.value)} className={INPUT_CLASS} />
        </label>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        <MuscleChecks
          label="Primary (counts 1 set)"
          selected={primary}
          blocked={secondary}
          disabled={readOnly}
          onToggle={(m) => setPrimary((p) => flip(p, m))}
        />
        <MuscleChecks
          label="Secondary (counts 0.5 set)"
          selected={secondary}
          blocked={primary}
          disabled={readOnly}
          onToggle={(m) => setSecondary((s) => flip(s, m))}
        />
      </div>
      {save.error && <p className="text-xs text-red-300">{save.error.message}</p>}
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={readOnly || save.isPending || primary.length === 0}
          className={BUTTON_CLASS}
          onClick={() => save.mutate({ exercise_key: exerciseKey, name: name.trim() || exerciseKey, primary, secondary })}
        >
          Save
        </button>
        {save.isSuccess && !save.isPending && <span className="text-xs text-accent">Saved</span>}
        {primary.length === 0 && <span className="text-[11px] text-ink-500">Pick at least one primary muscle</span>}
      </div>
    </div>
  );
}

function VolumeRow({ m, zones, scale, open, onToggle }: { m: VolumeMuscle; zones: FitnessZones; scale: number; open: boolean; onToggle: () => void }) {
  const pctOf = (v: number) => `${Math.min(100, (v / scale) * 100)}%`;
  return (
    <li className="border-b border-ink-800 last:border-0">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-3 py-1.5 text-left hover:bg-ink-800/40">
        <span className="w-20 shrink-0 text-xs text-ink-300">{titleCase(m.muscle)}</span>
        <span className="relative h-3 flex-1 overflow-hidden rounded-full bg-ink-800">
          <span
            className="absolute inset-y-0 bg-accent/10"
            style={{ left: pctOf(zones.building_max), width: `${((zones.target_max - zones.building_max) / scale) * 100}%` }}
          />
          <span className={`absolute inset-y-0 left-0 rounded-full ${zoneClass(m.zone)}`} style={{ width: pctOf(m.sets) }} />
          {[zones.below_minimum_max, zones.building_max, zones.target_max].map((b) => (
            <span key={b} className="absolute inset-y-0 w-px bg-ink-300/70" style={{ left: pctOf(b) }} />
          ))}
        </span>
        <span className="tabular w-10 shrink-0 text-right text-xs text-ink-200">{formatSets(m.sets)}</span>
        <Chip tone={zoneTone(m.zone)} className="hidden w-28 justify-center sm:inline-flex">
          {zoneLabel(m.zone)}
        </Chip>
      </button>
      {open && (
        <ul className="mb-2 ml-[5.75rem] space-y-0.5 text-xs">
          {m.exercises.length === 0 && <li className="text-ink-500">No sets this week</li>}
          {m.exercises.map((e) => (
            <li key={e.exercise_key} className="flex justify-between gap-2 text-ink-300">
              <span className="truncate">{e.name}</span>
              <span className="tabular text-ink-200">{formatSets(e.sets)}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function MapEditorList({ readOnly }: { readOnly: boolean }) {
  const q = useMuscleMap();
  if (q.error) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-24 w-full" />;
  const keys = Object.keys(q.data.map).sort((a, b) => q.data!.map[a].name.localeCompare(q.data!.map[b].name));
  return (
    <div className="space-y-2">
      {keys.length === 0 && <p className="text-sm text-ink-500">No exercises mapped yet</p>}
      {keys.map((k) => (
        <MuscleEntryEditor key={`${k}:${JSON.stringify(q.data!.map[k])}`} exerciseKey={k} initial={q.data!.map[k]} readOnly={readOnly} />
      ))}
    </div>
  );
}

function VolumeView({ data, readOnly }: { data: FitnessData; readOnly: boolean }) {
  const v = data.volume;
  const [history, setHistory] = useState(false);
  const [openMuscle, setOpenMuscle] = useState<Muscle | null>(null);
  const scale = volumeScaleMax(v.muscles, v.zones.target_max);
  const weeks = useMemo(() => v.weeks.map((wk) => ({ week_start: wk.week_start, ...wk.sets })), [v.weeks]);
  return (
    <>
      <section className={`${PANEL_CLASS} p-4`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SectionLabel className="mb-0">
            {history ? "Weekly sets per muscle, last 8 weeks" : `Sets per muscle, week of ${formatDateOnly(v.week_start)}`}
          </SectionLabel>
          <label className="inline-flex items-center gap-1 text-xs text-ink-300">
            <input type="checkbox" className="accent-[#4ade80]" checked={history} onChange={(e) => setHistory(e.target.checked)} /> Last 8 weeks
          </label>
        </div>
        {history ? (
          <div className="mt-2 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={weeks} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
                <XAxis dataKey="week_start" tickFormatter={dateTick} tick={TICK} axisLine={false} tickLine={false} />
                <YAxis tick={TICK} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(x) => `Week of ${formatDateOnly(String(x))}`} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={v.zones.building_max} stroke="#4d5a52" strokeDasharray="4 4" />
                <ReferenceLine y={v.zones.target_max} stroke="#4d5a52" strokeDasharray="4 4" />
                {MUSCLES.map((m) => (
                  <Line key={m} dataKey={m} name={m} stroke={MUSCLE_COLORS[m]} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <>
            <ul className="mt-2">
              {v.muscles.map((m) => (
                <VolumeRow
                  key={m.muscle}
                  m={m}
                  zones={v.zones}
                  scale={scale}
                  open={openMuscle === m.muscle}
                  onToggle={() => setOpenMuscle(openMuscle === m.muscle ? null : m.muscle)}
                />
              ))}
            </ul>
            <div className="mt-1 flex items-center gap-3 text-[10px] text-ink-500">
              <span className="w-20 shrink-0" />
              <span className="relative h-3 flex-1">
                {[v.zones.below_minimum_max, v.zones.building_max, v.zones.target_max].map((b) => (
                  <span key={b} className="absolute -translate-x-1/2" style={{ left: `${Math.min(100, (b / scale) * 100)}%` }}>
                    {b}
                  </span>
                ))}
              </span>
              <span className="w-10 shrink-0" />
              <span className="hidden w-28 sm:block" />
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(["below_minimum", "building", "target", "high"] as const).map((z) => (
                <span key={z} className="inline-flex items-center gap-1 text-[11px] text-ink-400">
                  <span className="h-2 w-2 rounded-sm" style={{ background: zoneColor(z) }} /> {zoneLabel(z)}
                </span>
              ))}
            </div>
          </>
        )}
      </section>

      <section className={`${PANEL_CLASS} p-4`}>
        <SectionLabel>Unmapped exercises</SectionLabel>
        {v.unmapped.length === 0 ? (
          <p className="text-sm text-ink-500">Every logged exercise is mapped</p>
        ) : (
          <>
            <p className="mb-2 text-xs text-ink-400">These sets were logged this week but count toward no muscle until the exercise is mapped.</p>
            <ul className="space-y-2">
              {v.unmapped.map((u) => (
                <li key={u.exercise_key}>
                  {readOnly ? (
                    <div className="flex justify-between text-sm">
                      <code className="font-mono text-xs text-ink-300">{u.exercise_key}</code>
                      <span className="tabular text-ink-400">{formatSets(u.sets)} sets</span>
                    </div>
                  ) : (
                    <>
                      <div className="mb-1 text-[11px] text-ink-400">{formatSets(u.sets)} sets this week</div>
                      <MuscleEntryEditor exerciseKey={u.exercise_key} readOnly={false} />
                    </>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {!readOnly && (
        <section className={`${PANEL_CLASS} p-4`}>
          <Disclosure label="Edit map">
            <MapEditorList readOnly={readOnly} />
          </Disclosure>
        </section>
      )}
    </>
  );
}

// ---- strength

function PrDot({ cx, cy, payload }: DotProps & { payload?: StrengthPoint }) {
  if (cx === undefined || cy === undefined || !payload) return null;
  return payload.pr ? <circle cx={cx} cy={cy} r={4} fill="#4ade80" stroke="#101513" strokeWidth={1.5} /> : <circle cx={cx} cy={cy} r={2} fill="#60a5fa" />;
}

function StrengthView({ data }: { data: FitnessData }) {
  const s = data.strength;
  const [chosen, setChosen] = useState("");
  const key = chosen || defaultExerciseKey(s.exercises);
  const ex = s.exercises.find((e) => e.exercise_key === key);
  return (
    <>
      <section className={`${PANEL_CLASS} p-4`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SectionLabel className="mb-0">Estimated one-rep max</SectionLabel>
          {s.exercises.length > 0 && (
            <select
              value={key}
              onChange={(e) => setChosen(e.target.value)}
              className="rounded border border-ink-700 bg-ink-900 px-2 py-1 text-sm text-ink-200"
              aria-label="Exercise"
            >
              {s.exercises.map((e) => (
                <option key={e.exercise_key} value={e.exercise_key}>
                  {e.name} ({e.sessions} sessions)
                </option>
              ))}
            </select>
          )}
        </div>
        {!ex ? (
          <p className="mt-2 text-sm text-ink-500">No strength data yet</p>
        ) : (
          <>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-ink-400">
              <span>
                Best <span className="tabular text-ink-200">{ex.best_e1rm.toFixed(1)} lb</span>
              </span>
              <span>
                <span className="tabular text-ink-200">{ex.points.filter((p) => p.pr).length}</span> PR sessions
              </span>
            </div>
            <div className="mt-2 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={ex.points} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                  <XAxis dataKey="date" tickFormatter={dateTick} tick={TICK} axisLine={false} tickLine={false} minTickGap={32} />
                  <YAxis domain={["dataMin - 5", "dataMax + 5"]} tick={TICK} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    labelFormatter={dateLabel}
                    formatter={(v: number, _n, item) => [`${Number(v).toFixed(1)} lb${(item.payload as StrengthPoint).pr ? ", PR" : ""}`, "e1RM"]}
                  />
                  <Line dataKey="e1rm" stroke="#60a5fa" strokeWidth={2} dot={<PrDot />} activeDot={{ r: 5 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3">
              <SectionLabel>Rep PRs</SectionLabel>
              {ex.rep_prs.length === 0 ? (
                <p className="text-sm text-ink-500">No rep PRs yet</p>
              ) : (
                <table className="w-full max-w-md text-xs">
                  <thead className="text-left text-ink-400">
                    <tr>
                      <th className="py-1 font-medium">Weight</th>
                      <th className="py-1 font-medium">Reps</th>
                      <th className="py-1 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ex.rep_prs.map((r) => (
                      <tr key={`${r.weight}-${r.reps}`} className="border-t border-ink-800">
                        <td className="tabular py-1 text-ink-200">{r.weight} lb</td>
                        <td className="tabular py-1 text-ink-200">{r.reps}</td>
                        <td className="py-1 text-ink-400">{formatDateOnly(r.date, "MMM d, yyyy")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </section>
      <section className={`${PANEL_CLASS} p-4`}>
        <SectionLabel>Recent PRs</SectionLabel>
        {s.recent_prs.length === 0 ? (
          <p className="text-sm text-ink-500">No PRs yet</p>
        ) : (
          <ul className="divide-y divide-ink-800 text-xs">
            {s.recent_prs.map((p, i) => (
              <li key={`${p.date}-${p.exercise_key}-${i}`} className="flex flex-wrap items-center gap-2 py-1.5">
                <span className="w-14 shrink-0 text-ink-400">{formatDateOnly(p.date)}</span>
                <span className="min-w-0 flex-1 truncate text-ink-200">{p.name}</span>
                <Chip tone={p.kind === "e1rm" ? "good" : "info"}>{p.kind === "e1rm" ? "e1RM PR" : "rep PR"}</Chip>
                <span className="tabular w-24 text-right text-ink-200">
                  {p.weight} x {p.reps}
                </span>
                <span className="tabular w-20 text-right text-ink-400">{p.e1rm === null ? "" : `e1RM ${p.e1rm.toFixed(1)}`}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

// ---- stalled

function StalledView({ data }: { data: FitnessData }) {
  const st = data.stalled;
  return (
    <section className={`${PANEL_CLASS} p-4`}>
      <SectionLabel>Stalled lifts, last {st.window_weeks} weeks</SectionLabel>
      {st.count === 0 ? (
        <p className="text-sm text-ink-500">No stalled lifts</p>
      ) : (
        <ul className="divide-y divide-ink-800">
          {st.items.map((it) => (
            <li key={it.exercise_key} className="flex flex-wrap items-center gap-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-ink-200">{it.name}</div>
                <div className="text-[11px] text-ink-400">{it.sessions} sessions</div>
              </div>
              <div className="h-10 w-32">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={it.sparkline} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
                    <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={dateLabel} formatter={(v: number) => [`${Number(v).toFixed(1)} lb`, "e1RM"]} />
                    <Line dataKey="e1rm" stroke="#fbbf24" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <Chip tone={it.pct_change < 0 ? "bad" : "warn"} className="tabular w-16 justify-center">
                {signed(it.pct_change)}%
              </Chip>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---- page

export function FitnessPage({ readOnly }: { readOnly: boolean }) {
  const { view } = useParams();
  const q = useFitness();
  if (!isFitnessView(view)) return <Navigate to="/fitness/weight" replace />;
  const env = q.data;
  const data = env?.data ?? null;
  const tab = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1 text-sm ${isActive ? "bg-ink-800 text-ink-200" : "text-ink-300 hover:bg-ink-700 hover:text-ink-200"}`;
  return (
    <main className="mx-auto max-w-[1400px] space-y-4 px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold text-ink-200">Fitness</h1>
        {data && <span className="text-xs text-ink-400">As of {formatDateOnly(data.as_of, "EEE, MMM d")}</span>}
      </div>
      <nav className="flex flex-wrap gap-1" aria-label="Fitness views">
        {FITNESS_VIEWS.map((v) => (
          <NavLink key={v} to={`/fitness/${v}`} className={tab}>
            {VIEW_TITLE[v]}
            {v === "stalled" && data && data.stalled.count > 0 && <span className="ml-1 text-amber-300">{data.stalled.count}</span>}
          </NavLink>
        ))}
      </nav>
      <Explainer view={view} />
      {q.error && !env && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
      {!env && !q.error && <Skeleton className="h-64 w-full" />}
      {env?.status === "disabled" && <SetupHint title="Fitness" vars={env.setup_hint} />}
      {env && env.status !== "disabled" && !data && <ErrorState message={env.error ?? "LockIn data has not loaded yet"} onRetry={() => q.refetch()} />}
      {data && view === "weight" && <WeightView data={data} readOnly={readOnly} />}
      {data && view === "consistency" && <ConsistencyView data={data} />}
      {data && view === "volume" && <VolumeView data={data} readOnly={readOnly} />}
      {data && view === "strength" && <StrengthView data={data} />}
      {data && view === "stalled" && <StalledView data={data} />}
    </main>
  );
}
