import { ChevronDown, Droplets, MapPin, Wind } from "lucide-react";
import { useState } from "react";
import { Bar, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSaveSettings, useWeather } from "../api/hooks";
import type { WeatherAlert, WeatherData } from "../api/types";
import { Card } from "../components/Card";
import { Chip } from "../components/Bars";
import { formatDateOnly, formatHour } from "../lib/format";
import { DynamicIcon } from "../lib/icons";

const BADGE_LABEL: Record<string, string> = { umbrella: "Umbrella", wind: "Windy", freeze: "Freeze tonight", uv: "High UV" };

function alertTone(sev: string): "bad" | "warn" | "info" {
  if (sev === "Extreme" || sev === "Severe") return "bad";
  if (sev === "Moderate") return "warn";
  return "info";
}

function AlertBanner({ alert }: { alert: WeatherAlert }) {
  const [open, setOpen] = useState(false);
  const tone = alertTone(alert.severity);
  const cls = tone === "bad" ? "border-red-500/50 bg-red-500/10 text-red-100" : tone === "warn" ? "border-amber-500/50 bg-amber-500/10 text-amber-100" : "border-sky-500/40 bg-sky-500/10 text-sky-100";
  return (
    <div className={`rounded-lg border ${cls}`}>
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm" aria-expanded={open}>
        <DynamicIcon name="triangle-alert" size={16} className="shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="font-semibold">{alert.event}</span>
          <span className="ml-2 text-xs opacity-80">{alert.severity}{alert.expires ? `, until ${formatHour(alert.expires)}` : ""}</span>
        </span>
        <ChevronDown size={16} className={`transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="space-y-2 px-3 pb-3 text-xs leading-relaxed opacity-90">
          {alert.headline && <p className="font-medium">{alert.headline}</p>}
          {alert.description && <p className="whitespace-pre-line">{alert.description}</p>}
          {alert.instruction && <p className="italic">{alert.instruction}</p>}
        </div>
      )}
    </div>
  );
}

export function WeatherBody({ data, kiosk }: { data: WeatherData; kiosk?: boolean }) {
  const unitT = data.units === "metric" ? "°C" : "°F";
  const unitW = data.units === "metric" ? "km/h" : "mph";
  const hours = data.next_12h.map((h) => ({ ...h, label: formatHour(h.time) }));
  return (
    <div className="space-y-3">
      {data.alerts.map((a) => (
        <AlertBanner key={a.id ?? a.event} alert={a} />
      ))}
      {data.alerts_error && <p className="text-[11px] text-amber-300">Alerts unavailable: {data.alerts_error}</p>}
      <div className="flex items-center gap-4">
        <DynamicIcon name={data.current.icon} size={kiosk ? 72 : 52} className="text-accent" />
        <div>
          <div className={`tabular ${kiosk ? "text-6xl" : "text-4xl"} font-semibold leading-none text-ink-200`}>
            {data.current.temp ?? "--"}
            <span className="text-xl text-ink-400">{unitT}</span>
          </div>
          <div className={`${kiosk ? "text-lg" : "text-sm"} text-ink-300`}>{data.current.label}</div>
          <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-ink-400">
            <span>Feels like {data.current.feels_like ?? "--"}{unitT}</span>
            <span className="inline-flex items-center gap-1">
              <Wind size={12} /> {data.current.wind_mph ?? "--"} {unitW}{data.current.gust_mph ? ` (gusts ${data.current.gust_mph})` : ""}
            </span>
            <span className="inline-flex items-center gap-1">
              <Droplets size={12} /> {data.current.humidity ?? "--"}%
            </span>
          </div>
        </div>
        <div className="ml-auto flex flex-col items-end gap-1">
          {data.badges.map((b) => (
            <Chip key={b} tone={b === "freeze" ? "info" : "warn"}>
              <DynamicIcon name={b} size={12} /> {BADGE_LABEL[b] ?? b}
            </Chip>
          ))}
          {data.aqi !== null && data.aqi >= 101 && <Chip tone="bad">AQI {data.aqi}</Chip>}
        </div>
      </div>
      <div className="h-28 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={hours} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
            <XAxis dataKey="label" tick={{ fill: "#97a69c", fontSize: 10 }} axisLine={false} tickLine={false} interval={1} />
            <YAxis yAxisId="t" domain={["dataMin - 5", "dataMax + 5"]} tick={{ fill: "#6b7a71", fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="p" orientation="right" domain={[0, 100]} hide />
            <Tooltip contentStyle={{ background: "#171e1a", border: "1px solid #2f3a33", fontSize: 12 }} labelStyle={{ color: "#c6d1ca" }} formatter={(v: number, name: string) => [name === "pop" ? `${v}%` : `${v}${unitT}`, name === "pop" ? "Rain chance" : "Temp"]} />
            <Bar yAxisId="p" dataKey="pop" fill="#60a5fa" opacity={0.45} radius={[2, 2, 0, 0]} isAnimationActive={false} />
            <Line yAxisId="t" type="monotone" dataKey="temp" stroke="#4ade80" strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center">
        {data.daily.map((d, i) => (
          <div key={d.date} className="rounded-lg bg-ink-800/60 px-1 py-2">
            <div className="text-[11px] text-ink-400">{i === 0 ? "Today" : formatDateOnly(d.date, "EEE")}</div>
            <DynamicIcon name={d.icon} size={kiosk ? 26 : 20} className="mx-auto my-1 text-ink-200" />
            <div className="tabular text-xs text-ink-200">
              {d.hi ?? "--"}
              <span className="text-ink-400"> / {d.lo ?? "--"}</span>
            </div>
            {d.pop >= 20 && <div className="text-[10px] text-sky-300">{d.pop}%</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function WeatherWidget({ kiosk, location }: { kiosk?: boolean; location?: string }) {
  const q = useWeather(location);
  const save = useSaveSettings();
  const data = q.data?.data ?? null;
  const picker =
    data && data.available.length > 1 && !kiosk ? (
      <label className="inline-flex items-center gap-1 text-xs text-ink-400">
        <MapPin size={12} />
        <select value={data.location} onChange={(e) => save.mutate({ weather_location: e.target.value })} className="rounded border border-ink-700 bg-ink-800 px-1 py-0.5 text-xs text-ink-200">
          {data.available.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
    ) : data ? (
      <span className="inline-flex items-center gap-1 text-xs text-ink-400">
        <MapPin size={12} /> {data.location}
      </span>
    ) : null;
  return (
    <Card title="Weather" envelope={q.data} error={q.error} onRetry={() => q.refetch()} actions={picker} kiosk={kiosk}>
      {(d) => <WeatherBody data={d} kiosk={kiosk} />}
    </Card>
  );
}
