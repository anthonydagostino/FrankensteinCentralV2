import { Activity, AlertTriangle, BadgeDollarSign, CalendarDays, CloudSun, LayoutDashboard, TrainFront, Wallet } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAttention, useBenefits, useCalendar, useContainers, useFinance, usePlex, useTraining, useTransit, useVault, useWeather } from "../api/hooks";
import type { Envelope, PublicConfig } from "../api/types";
import { Chip } from "../components/Bars";
import { Money } from "../components/Money";
import { PrivacyToggle } from "../components/PrivacyToggle";
import { formatDateOnly, formatHour, formatTime, greeting } from "../lib/format";
import { benefitSummary, homeGlance, moneyGlance, trainingGlance, transitGlance, upcomingEvents, weatherGlance, writeViewMode } from "../lib/glance";
import type { TransitRow } from "../lib/glance";
import { DynamicIcon } from "../lib/icons";
import { PANEL_CLASS, SEVERITY_CLASS } from "../lib/ui";
import { useNow } from "../lib/useNow";
import { TZ } from "../lib/format";
import { formatInTimeZone } from "date-fns-tz";
import { Bar, BarChart, ResponsiveContainer } from "recharts";
import { ProgressBar } from "../components/Bars";

/** A panel that never grows the page: content past its box is clipped, not scrolled. */
function Panel({
  title,
  icon,
  envelope,
  children,
  className = "",
  order = 0,
}: {
  title: string;
  icon: ReactNode;
  envelope?: Envelope<unknown>;
  children: ReactNode;
  className?: string;
  /** Position in the entrance sequence: each panel arrives 60ms after the one before (stage the focus). */
  order?: number;
}) {
  const dot = !envelope
    ? "bg-ink-500"
    : envelope.stale || envelope.status === "degraded"
      ? "bg-amber-400"
      : envelope.status === "ok"
        ? "bg-accent"
        : "bg-red-500";
  return (
    <section
      aria-label={title}
      className={`rise-in flex min-h-0 flex-col overflow-hidden ${PANEL_CLASS} p-4 ${className}`}
      style={{ animationDelay: `${order * 60}ms` }}
    >
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-400">
        <span className={`h-2 w-2 rounded-full ${dot}`} />
        {icon}
        {title}
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </section>
  );
}

const Empty = ({ text }: { text: string }) => <p className="text-sm text-ink-500">{text}</p>;

/** One direction of the train board: departure time, minutes away, status, and whether it runs through. */
function TrainBoard({ heading, rows }: { heading: string; rows: TransitRow[] }) {
  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-500">{heading}</div>
      {rows.length === 0 ? (
        <Empty text="No trains in the next few hours" />
      ) : (
        <ul className="space-y-1.5">
          {rows.map((r) => (
            <li
              key={r.train_id}
              className={`rounded-lg px-3 py-1.5 short:py-1 short:[&:nth-child(n+4)]:hidden ${r.state === "cancelled" ? "bg-ink-800/30 text-ink-500" : "bg-ink-800/50"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`tabular whitespace-nowrap text-lg ${r.state === "cancelled" ? "line-through" : "text-ink-200"}`}>
                  {formatTime(r.departs)}
                </span>
                <Chip tone={r.tone}>{r.label}</Chip>
              </div>
              <div className="truncate text-xs text-ink-400">
                {r.state === "cancelled" ? "" : r.minutes === 0 ? "now · " : `in ${r.minutes} min · `}
                {r.direct ? "Direct" : r.via ? `via ${r.via}` : r.destination}
                {r.track ? ` · Track ${r.track}` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function GlancePage({ config }: { config?: PublicConfig }) {
  const now = useNow(1000);
  const navigate = useNavigate();
  const attention = useAttention(config?.selected_location);
  const calendar = useCalendar(3);
  const weather = useWeather(config?.selected_location);
  const finance = useFinance();
  const training = useTraining();
  const benefits = useBenefits();
  const transit = useTransit();
  const plex = usePlex();
  const vault = useVault();
  const containers = useContainers();

  const items = attention.data?.data?.items ?? [];
  const events = upcomingEvents(calendar.data?.data, now, 6);
  const w = weatherGlance(weather.data?.data);
  const money = moneyGlance(finance.data?.data);
  const train = trainingGlance(training.data?.data);
  const cards = benefitSummary(benefits.data?.data);
  const trains = transitGlance(transit.data?.data, now);
  const home = homeGlance(plex.data?.data, vault.data?.data, containers.data?.data);
  const [time, ampm, day] = formatInTimeZone(now, TZ, "h:mm|a|EEEE, MMMM d").split("|");

  return (
    <main className="flex h-screen flex-col gap-3 overflow-hidden px-4 py-3" aria-label="Glance">
      <div className="flex items-center gap-4">
        <div className="tabular text-5xl font-semibold leading-none text-ink-200">
          {time}
          <span className="ml-1 text-xl text-ink-400">{ampm}</span>
        </div>
        <div className="leading-tight">
          <div className="text-lg text-ink-200">{day}</div>
          <div className="text-sm text-ink-400">{config ? greeting(now, config.owner_name) : ""}</div>
        </div>
        {w && (
          <div className="ml-6 flex items-center gap-3 text-ink-200">
            <DynamicIcon name={w.icon} size={36} className="text-ink-300" />
            <div className="leading-tight">
              <div className="text-3xl font-semibold">{w.temp !== null ? `${Math.round(w.temp)}°` : "--"}</div>
              <div className="text-xs text-ink-400">
                {w.label}
                {w.hi !== null && w.lo !== null ? ` · ${Math.round(w.hi)}° / ${Math.round(w.lo)}°` : ""}
              </div>
            </div>
          </div>
        )}
        <div className="ml-auto flex items-center gap-2">
          <PrivacyToggle />
          <button
            type="button"
            onClick={() => {
              writeViewMode("full");
              navigate("/");
            }}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-ink-700 px-3 text-sm text-ink-300 hover:border-accent/50 hover:text-ink-200"
            title="Switch to the full dashboard"
          >
            <LayoutDashboard size={16} /> Full dashboard
          </button>
        </div>
      </div>

      <div className="flex h-9 items-center gap-2 overflow-hidden" aria-label="Attention">
        {items.length === 0 ? (
          <span className="text-sm text-accent">All clear</span>
        ) : (
          items.slice(0, 4).map((item) => (
            <span
              key={`${item.source}:${item.title}`}
              className={`inline-flex max-w-[26rem] items-center gap-2 truncate rounded-lg border px-3 py-1 text-sm ${SEVERITY_CLASS[item.severity]}`}
            >
              <DynamicIcon name={item.icon} size={14} className="shrink-0" />
              <span className="truncate">{item.title}</span>
            </span>
          ))
        )}
        {items.length > 4 && <span className="text-xs text-ink-400">+{items.length - 4} more</span>}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-3 grid-rows-2 gap-3">
        <Panel title="Calendar" order={1} icon={<CalendarDays size={14} />} envelope={calendar.data}>
          {!calendar.data?.data ? (
            <Empty text="No calendar data" />
          ) : events.length === 0 ? (
            <Empty text="Nothing coming up in the next three days" />
          ) : (
            <ul className="space-y-1.5">
              {events.map((ev, i) => {
                const first = i === 0 || events[i - 1].day !== ev.day;
                return (
                  <li key={ev.id} className="short:[&:nth-child(n+4)]:hidden">
                    {first && (
                      <div className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-ink-500 first:mt-0">
                        {ev.day === "today" ? "Today" : ev.day === "tomorrow" ? "Tomorrow" : formatDateOnly(ev.date, "EEEE")}
                      </div>
                    )}
                    <div className={`flex items-center gap-3 rounded-lg px-3 py-2.5 short:py-1.5 ${ev.in_progress ? "bg-accent/10" : "bg-ink-800/50"}`}>
                      <span className="h-9 w-1 shrink-0 rounded" style={{ background: ev.color }} />
                      <span className="w-24 shrink-0 text-base text-ink-400">{ev.all_day ? "All day" : formatTime(ev.start)}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-lg text-ink-200">{ev.title}</span>
                        {ev.location && !/^https?:\/\//i.test(ev.location) && <span className="block truncate text-xs text-ink-500">{ev.location}</span>}
                      </span>
                      {ev.in_progress && <Chip tone="good">now</Chip>}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        <Panel title="Weather" order={2} icon={<CloudSun size={14} />} envelope={weather.data}>
          {!w ? (
            <Empty text="No weather data" />
          ) : (
            <div className="flex h-full flex-col justify-between">
              <div className="grid grid-cols-5 gap-2 text-center">
                {w.hours.map((h) => (
                  <div key={h.time} className="rounded-lg bg-ink-800/50 py-3 short:py-2">
                    <div className="text-xs text-ink-400">{formatHour(h.time)}</div>
                    <DynamicIcon name={h.icon} size={28} className="mx-auto my-1.5 text-ink-300" />
                    <div className="text-xl text-ink-200">{h.temp !== null ? `${Math.round(h.temp)}°` : "--"}</div>
                    <div className={`text-xs ${h.pop >= 20 ? "text-sky-300" : "text-transparent"}`}>{h.pop}%</div>
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between text-sm text-ink-400 short:hidden">
                <span>Feels {w.feels_like !== null ? `${Math.round(w.feels_like)}°` : "--"}</span>
                <span>Wind {w.wind_mph !== null ? `${Math.round(w.wind_mph)} mph` : "--"}</span>
                <span>Humidity {w.humidity !== null ? `${Math.round(w.humidity)}%` : "--"}</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {w.days.map((d) => (
                  <div key={d.date} className="flex items-center gap-3 rounded-lg bg-ink-800/50 px-3 py-2">
                    <DynamicIcon name={d.icon} size={22} className="shrink-0 text-ink-300" />
                    <div className="min-w-0 leading-tight">
                      <div className="text-xs text-ink-400">{formatDateOnly(d.date, "EEE")}</div>
                      <div className="text-base text-ink-200">
                        {d.hi !== null ? `${Math.round(d.hi)}°` : "--"} <span className="text-ink-500">/ {d.lo !== null ? `${Math.round(d.lo)}°` : "--"}</span>
                      </div>
                      <div className={`text-xs short:hidden ${d.pop >= 20 ? "text-sky-300" : "text-transparent"}`}>{d.pop}% rain</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex min-h-6 items-center gap-2 text-sm text-ink-300">
                {w.alerts > 0 && (
                  <Chip tone="bad">
                    <AlertTriangle size={12} /> {w.alerts} alert{w.alerts > 1 ? "s" : ""}
                  </Chip>
                )}
                {w.badges.map((b) => (
                  <Chip key={b} tone="info">
                    {b}
                  </Chip>
                ))}
                {w.alerts === 0 && w.badges.length === 0 && <span className="text-ink-500">No alerts</span>}
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Money" order={3} icon={<Wallet size={14} />} envelope={finance.data}>
          {!money ? (
            <Empty text="No finance data" />
          ) : (
            <div className="flex h-full flex-col justify-between">
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-xs text-ink-400">Net worth</div>
                  <div className="text-5xl font-semibold text-ink-200 short:text-4xl">
                    <Money value={money.net_worth} whole strong />
                  </div>
                </div>
                {money.stale && <Chip tone="warn">stale</Chip>}
              </div>
              {money.daily.length > 1 && (
                <div className="min-h-0 flex-1 py-3" aria-label="Daily spend this month">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={money.daily} margin={{ top: 0, right: 0, bottom: 0, left: 0 }} barCategoryGap="20%">
                      <Bar dataKey="amount" fill="#4ade80" fillOpacity={0.55} radius={[2, 2, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <div className="text-xs text-ink-400">Spent this month</div>
                  <div className="text-2xl text-ink-200">
                    <Money value={money.mtd_spend} whole />
                  </div>
                  {money.pace && (
                    <div className={`text-xs ${money.pace_tone === "warn" ? "text-amber-300" : money.pace_tone === "good" ? "text-accent" : "text-ink-400"}`}>
                      {money.pace}
                    </div>
                  )}
                </div>
                <div>
                  <div className="text-xs text-ink-400">Left to spend</div>
                  <div className="text-2xl text-ink-200">{money.left_to_spend === null ? "--" : <Money value={money.left_to_spend} whole />}</div>
                  <div className="text-xs text-ink-500">after bills and budgets</div>
                </div>
                <div>
                  <div className="text-xs text-ink-400">Bills in 7 days</div>
                  <div className="text-2xl text-ink-200">{money.bills_count === 0 ? "None" : <Money value={money.bills_total} whole />}</div>
                  {money.bills_count > 0 && <div className="text-xs text-ink-400">{money.bills_count} due</div>}
                </div>
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Trains" order={4} icon={<TrainFront size={14} />} envelope={transit.data}>
          {!trains ? (
            <Empty text="No train data" />
          ) : (
            <div className="grid h-full grid-cols-2 gap-4">
              <TrainBoard heading={`${trains.from} to ${trains.to}`} rows={trains.outbound} />
              <TrainBoard heading={`${trains.to} to ${trains.from}`} rows={trains.inbound} />
            </div>
          )}
        </Panel>

        <Panel title="Lock-In" order={5} icon={<Activity size={14} />} envelope={training.data}>
          {!train ? (
            <Empty text="No training data" />
          ) : (
            <div className="flex h-full flex-col justify-between">
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-xs text-ink-400">Sessions this week</div>
                  <div className="text-5xl font-semibold text-ink-200 short:text-4xl">{train.sessions}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xl text-ink-200">{train.streak_weeks} wk streak</div>
                  {train.risk === "at_risk" && <Chip tone="warn">streak at risk</Chip>}
                  {train.risk === "lost" && <Chip tone="bad">streak lost</Chip>}
                  {train.phase && (train.risk === "safe" || train.risk === "ok") && <div className="text-xs text-ink-400">{train.phase}</div>}
                </div>
              </div>
              {train.week && (
                <div className="grid grid-cols-7 gap-2">
                  {train.week.map((d) => (
                    <div
                      key={d.date}
                      className={`rounded-md py-3 text-center text-base short:py-2 ${d.done ? "bg-accent/25 text-accent" : d.today ? "border border-ink-500 text-ink-200" : d.future ? "bg-ink-800/40 text-ink-500" : "bg-ink-800/60 text-ink-500"}`}
                    >
                      {d.label}
                    </div>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <div className="text-xs text-ink-400">Weight, 7 day avg</div>
                  <div className="text-2xl text-ink-200">{train.weight.avg7 !== null ? `${train.weight.avg7} lb` : "--"}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-400">Weekly change</div>
                  <div className={`text-2xl ${train.weight.on_track === false ? "text-amber-300" : "text-ink-200"}`}>
                    {train.weight.weekly_change !== null ? `${train.weight.weekly_change > 0 ? "+" : ""}${train.weight.weekly_change} lb` : "--"}
                  </div>
                  {train.weight.target !== null && (
                    <div className="text-xs text-ink-500">
                      target {train.weight.target > 0 ? "+" : ""}
                      {train.weight.target} lb/wk
                    </div>
                  )}
                </div>
                <div>
                  <div className="text-xs text-ink-400">Today</div>
                  <div className="text-2xl text-ink-200">{train.trained_today ? "Trained" : train.next ? train.next : "Rest"}</div>
                  <div className={`text-xs ${train.weighed_today ? "text-ink-500" : "text-amber-300"}`}>
                    {train.weighed_today ? "Weighed in" : "No weigh-in yet"}
                  </div>
                </div>
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Amex benefits" order={6} icon={<BadgeDollarSign size={14} />} envelope={benefits.data}>
          {cards.length === 0 ? (
            <Empty text="No benefits data" />
          ) : (
            <div className="flex h-full flex-col justify-between">
              <div className="grid grid-cols-2 gap-4">
                {cards.map((c) => (
                  <div key={c.card}>
                    <div className="text-xs text-ink-400">{c.label}</div>
                    <div className="text-3xl font-semibold text-ink-200">
                      {c.used} <span className="text-base font-normal text-ink-400">of {c.total} used</span>
                    </div>
                    <ProgressBar value={c.used} max={Math.max(c.total, 1)} className="my-2" />
                    <div className="text-xs text-ink-400 short:hidden">
                      {c.open} open{c.pending ? `, ${c.pending} pending` : ""}
                    </div>
                  </div>
                ))}
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">Expiring soon</div>
                <ul className="space-y-1.5 text-base">
                  {cards
                    .flatMap((c) => c.expiring.map((e) => ({ ...e, card: c.label })))
                    .sort((a, b) => a.days_left - b.days_left)
                    .slice(0, 5)
                    .map((e) => (
                      <li
                        key={`${e.card}:${e.name}`}
                        className="flex items-center justify-between gap-2 rounded-lg bg-ink-800/50 px-3 py-1.5 short:py-1 short:[&:nth-child(n+4)]:hidden"
                      >
                        <span className="min-w-0 truncate text-ink-200">
                          {e.name} <span className="text-xs text-ink-500">{e.card}</span>
                        </span>
                        <span className="shrink-0 text-amber-300">
                          <Money open value={e.remaining} /> · {e.days_left}d
                        </span>
                      </li>
                    ))}
                  {cards.every((c) => c.expiring.length === 0) && <li className="text-sm text-ink-500">Nothing expiring soon</li>}
                </ul>
              </div>
            </div>
          )}
        </Panel>
      </div>

      <div className="flex h-10 items-center gap-8 text-base text-ink-300" aria-label="Home">
        <span className="inline-flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${home.plex_ok ? "bg-accent" : "bg-red-500"}`} />
          {home.plex}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${home.vault === "online" ? "bg-accent" : home.vault === "down" ? "bg-red-500" : "bg-ink-500"}`} />
          Vault {home.vault}
        </span>
        {home.containers && (
          <span className="inline-flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${home.containers.unhealthy || home.containers.stopped ? "bg-amber-400" : "bg-accent"}`} />
            {home.containers.running} running{home.containers.stopped ? `, ${home.containers.stopped} stopped` : ""}
            {home.containers.unhealthy ? `, ${home.containers.unhealthy} unhealthy` : ""}
          </span>
        )}
        <Link to="/" className="ml-auto text-xs text-ink-500 hover:text-ink-300">
          Full dashboard
        </Link>
      </div>
    </main>
  );
}
