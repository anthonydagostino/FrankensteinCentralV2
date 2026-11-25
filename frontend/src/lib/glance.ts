import type {
  BenefitsData,
  CalEvent,
  CalendarData,
  ContainersData,
  FinanceSummary,
  PlexData,
  TrainingData,
  TransitData,
  TransitDeparture,
  VaultData,
  WeatherData,
} from "../api/types";

/** The glance view: one fixed screen of the few numbers worth a look on the way out the door. Pure helpers live here. */

export const VIEW_KEY = "fc.view";
export type ViewMode = "full" | "glance";

export function readViewMode(): ViewMode {
  try {
    return localStorage.getItem(VIEW_KEY) === "glance" ? "glance" : "full";
  } catch {
    return "full";
  }
}

export function writeViewMode(mode: ViewMode): void {
  try {
    localStorage.setItem(VIEW_KEY, mode);
  } catch {
    /* private window or blocked storage: the choice just does not stick */
  }
}

export interface GlanceEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  day: "today" | "tomorrow" | "later";
  date: string;
  in_progress: boolean;
  join_url: string | null;
  color: string;
  location: string | null;
}

/** Upcoming events across the next days: what is still ahead today, then tomorrow and later, up to `limit`. */
export function upcomingEvents(data: CalendarData | null | undefined, now: Date, limit = 7): GlanceEvent[] {
  if (!data) return [];
  const out: GlanceEvent[] = [];
  data.days.forEach((day, index) => {
    for (const ev of day.events) {
      if (!ev.all_day && new Date(ev.end).getTime() < now.getTime()) continue; // over
      out.push({
        id: ev.id,
        title: ev.title,
        start: ev.start,
        end: ev.end,
        all_day: ev.all_day,
        day: index === 0 ? "today" : index === 1 ? "tomorrow" : "later",
        date: day.date,
        in_progress: ev.in_progress,
        join_url: ev.join_url,
        color: ev.color,
        location: ev.location,
      });
    }
  });
  return out.slice(0, limit);
}

export const isTodayEvent = (ev: Pick<CalEvent, "all_day">): boolean => !ev.all_day;

export interface BenefitCardGlance {
  card: string;
  label: string;
  used: number;
  pending: number;
  open: number;
  total: number;
  expiring: { name: string; days_left: number; remaining: string }[];
}

/** Per card: how many current-period benefits are used, pending, or still open, plus what expires soonest. */
export function benefitSummary(data: BenefitsData | null | undefined): BenefitCardGlance[] {
  if (!data) return [];
  return data.cards.map((card) => {
    const current = card.benefits.filter((b) => b.current);
    const used = current.filter((b) => b.current!.status === "used").length;
    const pending = current.filter((b) => b.current!.status === "pending").length;
    const expiring = current
      .filter((b) => b.current!.expiring_soon)
      .map((b) => ({ name: b.name, days_left: b.current!.days_left, remaining: b.current!.remaining }))
      .sort((a, b) => a.days_left - b.days_left)
      .slice(0, 3);
    return { card: card.card, label: card.label, used, pending, open: current.length - used - pending, total: current.length, expiring };
  });
}

export interface MoneyGlance {
  net_worth: string;
  mtd_spend: string;
  left_to_spend: string | null;
  pace: string | null;
  pace_tone: "good" | "warn" | "neutral";
  bills_count: number;
  bills_total: number;
  daily: { date: string; amount: number }[];
  stale: boolean;
}

/** Net worth, month to date spend with its pace against last month, and bills due in the next 7 days. */
export function moneyGlance(f: FinanceSummary | null | undefined): MoneyGlance | null {
  if (!f) return null;
  const due = f.bills.filter((b) => !b.paid && b.days >= 0 && b.days <= 7);
  const pct = f.pace_pct === null ? null : Math.abs(Math.round(f.pace_pct));
  const pace = f.pace && pct !== null ? `${pct}% ${f.pace === "ahead" ? "above" : "below"} last month` : null;
  return {
    net_worth: f.net_worth,
    mtd_spend: f.mtd_spend,
    left_to_spend: f.left_to_spend,
    pace,
    pace_tone: f.pace === "ahead" ? "warn" : f.pace === "behind" ? "good" : "neutral",
    bills_count: due.length,
    bills_total: due.reduce((sum, b) => sum + Number(b.amount), 0),
    daily: f.daily_spend.map((d) => ({ date: d.date, amount: Number(d.amount) })),
    stale: f.freshness.stale,
  };
}

export interface WeatherGlance {
  temp: number | null;
  label: string;
  icon: string;
  hi: number | null;
  lo: number | null;
  pop: number;
  feels_like: number | null;
  wind_mph: number | null;
  humidity: number | null;
  hours: { time: string; temp: number | null; icon: string; pop: number }[];
  days: { date: string; label: string; hi: number | null; lo: number | null; icon: string; pop: number }[];
  alerts: number;
  badges: string[];
}

/** Now, today's range, every other hour of the next ten, the next three days, and how many alerts are active. */
export function weatherGlance(w: WeatherData | null | undefined): WeatherGlance | null {
  if (!w) return null;
  const today = w.daily[0];
  return {
    temp: w.current.temp,
    label: w.current.label,
    icon: w.current.icon,
    hi: today?.hi ?? null,
    lo: today?.lo ?? null,
    pop: today?.pop ?? 0,
    feels_like: w.current.feels_like,
    wind_mph: w.current.wind_mph,
    humidity: w.current.humidity,
    hours: w.next_12h
      .filter((_, i) => i % 2 === 0)
      .slice(0, 5)
      .map((h) => ({ time: h.time, temp: h.temp, icon: h.icon, pop: h.pop })),
    days: w.daily.slice(1, 4).map((d) => ({ date: d.date, label: d.label, hi: d.hi, lo: d.lo, icon: d.icon, pop: d.pop })),
    alerts: w.alerts.length,
    badges: w.badges.slice(0, 2),
  };
}

export interface TrainingGlance {
  sessions: string;
  week: TrainingData["week"];
  streak_weeks: number;
  next: string | null;
  trained_today: boolean;
  weighed_today: boolean;
  risk: TrainingData["streak_risk"];
  phase: string | null;
  weight: { avg7: number | null; weekly_change: number | null; target: number | null; on_track: boolean | null };
}

export function trainingGlance(t: TrainingData | null | undefined): TrainingGlance | null {
  if (!t) return null;
  return {
    sessions: `${t.sessions_this_week} / ${t.sessions_planned}`,
    week: t.week,
    streak_weeks: t.streak_weeks,
    next: t.next_session?.name ?? null,
    trained_today: t.trained_today,
    weighed_today: t.weighed_today,
    risk: t.streak_risk,
    phase: t.phase.name ? `${t.phase.name}${t.phase.week ? ` wk ${t.phase.week}` : ""}${t.phase.deload ? " (deload)" : ""}` : null,
    weight: { avg7: t.weight.avg7, weekly_change: t.weight.weekly_change, target: t.weight.target_weekly_change, on_track: t.weight.on_track },
  };
}

export interface HomeGlance {
  plex: string;
  plex_ok: boolean;
  vault: "online" | "down" | "unknown";
  containers: { running: number; stopped: number; unhealthy: number } | null;
}

/** One line for the house: what Plex is playing, whether the vault answers, and container counts. */
export function homeGlance(plex: PlexData | null | undefined, vault: VaultData | null | undefined, containers: ContainersData | null | undefined): HomeGlance {
  let line = "Plex offline";
  let ok = false;
  if (plex?.server.online) {
    ok = true;
    const s = plex.sessions[0];
    line = s ? `${s.title}${s.user ? ` for ${s.user}` : ""}${plex.sessions.length > 1 ? ` and ${plex.sessions.length - 1} more` : ""}` : "Nothing playing";
  }
  return {
    plex: line,
    plex_ok: ok,
    vault: vault ? (vault.online ? "online" : "down") : "unknown",
    containers: containers ? { running: containers.summary.running, stopped: containers.summary.stopped, unhealthy: containers.summary.unhealthy } : null,
  };
}

export interface TransitRow extends TransitDeparture {
  /** Whole minutes until the train leaves, never negative. */
  minutes: number;
  /** Short status for the board: "on time", "6 min late", "boarding", "cancelled". */
  label: string;
  tone: "good" | "warn" | "bad" | "neutral";
}

export interface TransitGlance {
  from: string;
  to: string;
  via: string | null;
  outbound: TransitRow[];
  inbound: TransitRow[];
  messages: string[];
}

export const shortStation = (name: string): string => name.replace(/ Penn Station$/i, "").replace(/^New York$/i, "New York");

function transitRow(d: TransitDeparture, now: Date): TransitRow {
  const minutes = Math.max(0, Math.round((new Date(d.departs).getTime() - now.getTime()) / 60_000));
  const label = d.state === "cancelled" ? "cancelled" : d.state === "boarding" ? "boarding" : d.state === "delayed" ? `${d.delay_min} min late` : "on time";
  const tone = d.state === "cancelled" ? "bad" : d.state === "delayed" ? "warn" : d.state === "boarding" ? "good" : "neutral";
  return { ...d, via: d.via ? shortStation(d.via) : null, minutes, label, tone };
}

/** Both directions of the train board with minutes until departure, up to `limit` each. */
export function transitGlance(t: TransitData | null | undefined, now: Date, limit = 5): TransitGlance | null {
  if (!t) return null;
  const rows = (list: TransitDeparture[]) =>
    list
      .filter((d) => d.state !== "departed")
      .map((d) => transitRow(d, now))
      .slice(0, limit);
  return {
    from: shortStation(t.from.name),
    to: shortStation(t.to.name),
    via: t.via ? shortStation(t.via.name) : null,
    outbound: rows(t.outbound),
    inbound: rows(t.inbound),
    messages: t.messages,
  };
}
