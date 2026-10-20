import { ExternalLink, MapPin, Video } from "lucide-react";
import { useMemo, useState } from "react";
import { useCalendar } from "../api/hooks";
import type { CalEvent, CalendarData } from "../api/types";
import { Card } from "../components/Card";
import { Modal } from "../components/Modal";
import { formatDate, formatDateOnly, formatTime, minutesLabel } from "../lib/format";

function EventRow({ ev, onOpen, compact }: { ev: CalEvent; onOpen: (e: CalEvent) => void; compact?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(ev)}
      className={`flex w-full items-start gap-2 rounded-md px-2 py-1 text-left hover:bg-ink-800 ${ev.tentative ? "border border-dashed border-ink-500" : ""} ${ev.in_progress ? "bg-accent/10" : ""}`}
    >
      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: ev.color }} />
      <span className="min-w-0 flex-1">
        <span className={`block truncate ${compact ? "text-xs" : "text-sm"} text-ink-200`}>{ev.title}</span>
        <span className="block truncate text-[11px] text-ink-400">
          {ev.all_day ? "All day" : `${formatTime(ev.start)} to ${formatTime(ev.end)}`}
          {ev.location ? ` · ${ev.location}` : ""}
        </span>
      </span>
      {ev.join_url && <Video size={14} className="mt-1 shrink-0 text-sky-300" />}
    </button>
  );
}

function MiniMonth({ density, today }: { density: Record<string, number>; today: string }) {
  const cells = useMemo(() => {
    const [y, m] = today.split("-").map(Number);
    const first = new Date(Date.UTC(y, m - 1, 1));
    const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
    const lead = first.getUTCDay();
    const out: { key: string; day: number | null; count: number; isToday: boolean }[] = [];
    for (let i = 0; i < lead; i++) out.push({ key: `lead-${i}`, day: null, count: 0, isToday: false });
    for (let d = 1; d <= daysInMonth; d++) {
      const key = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      out.push({ key, day: d, count: density[key] ?? 0, isToday: key === today });
    }
    return { cells: out, title: formatDateOnly(today, "MMMM yyyy") };
  }, [density, today]);
  return (
    <div>
      <div className="mb-1 text-[11px] font-medium text-ink-400">{cells.title}</div>
      <div className="grid grid-cols-7 gap-0.5 text-center text-[10px]">
        {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
          <div key={i} className="text-ink-500">
            {d}
          </div>
        ))}
        {cells.cells.map((c) => (
          <div key={c.key} className={`flex h-6 flex-col items-center justify-center rounded ${c.isToday ? "bg-accent/20 text-accent" : "text-ink-300"}`}>
            {c.day && (
              <>
                <span className="leading-none">{c.day}</span>
                <span className="mt-0.5 block rounded-full bg-sky-300" style={{ width: c.count ? Math.min(3 + c.count * 1.5, 8) : 0, height: c.count ? Math.min(3 + c.count * 1.5, 8) : 0 }} />
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function NextLine({ data, large }: { data: CalendarData; large?: boolean }) {
  const n = data.next_event;
  if (!n) return <div className={`${large ? "text-lg" : "text-sm"} text-ink-400`}>Nothing else scheduled</div>;
  const hours = n.minutes_until / 60;
  const when = n.in_progress ? "Now" : hours > 2 ? `at ${formatTime(n.start)}` : `in ${minutesLabel(n.minutes_until)}`;
  return (
    <div className={`flex flex-wrap items-center gap-2 ${large ? "text-lg" : "text-sm"}`}>
      <span className="text-ink-400">{n.in_progress ? "Now:" : "Next:"}</span>
      <span className="font-medium text-ink-200">{n.title}</span>
      {!n.in_progress && <span className="text-accent">{when}</span>}
      {n.join_url && (
        <a href={n.join_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded border border-sky-500/40 px-2 py-0.5 text-xs text-sky-300 hover:bg-sky-500/10">
          <Video size={12} /> Join
        </a>
      )}
    </div>
  );
}

export function CalendarBody({ data, kiosk, onlyToday }: { data: CalendarData; kiosk?: boolean; onlyToday?: boolean }) {
  const [open, setOpen] = useState<CalEvent | null>(null);
  const today = data.days[0];
  const rest = data.days.slice(1, 7);
  const todayDate = today?.date ?? data.now.slice(0, 10);
  return (
    <div className="space-y-3">
      <NextLine data={data} large={kiosk} />
      <div className={`grid min-w-0 gap-4 ${onlyToday ? "grid-cols-1" : "md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]"}`}>
        <div className="min-w-0">
          <div className="mb-1 flex items-baseline justify-between">
            <span className={`${kiosk ? "text-base" : "text-xs"} font-semibold uppercase tracking-wide text-ink-400`}>Today</span>
            <span className="text-[11px] text-ink-500">{formatDateOnly(todayDate, "EEEE, MMM d")}</span>
          </div>
          {today && today.events.length === 0 && <p className="px-2 text-sm text-ink-400">No events today</p>}
          <div className="space-y-0.5">
            {today?.events.filter((e) => e.all_day).map((e) => <EventRow key={e.id} ev={e} onOpen={setOpen} />)}
            {today?.events.filter((e) => !e.all_day).map((e) => <EventRow key={e.id} ev={e} onOpen={setOpen} />)}
          </div>
        </div>
        {!onlyToday && (
          <div className="min-w-0 space-y-2">
            {rest.map((d) => (
              <div key={d.date}>
                <div className="flex items-baseline justify-between px-2">
                  <span className="text-xs font-semibold text-ink-300">{d.label}</span>
                  <span className="text-[10px] text-ink-500">{formatDateOnly(d.date, "MMM d")}</span>
                </div>
                {d.events.length === 0 ? <p className="px-2 text-[11px] text-ink-500">Free</p> : d.events.map((e) => <EventRow key={e.id} ev={e} onOpen={setOpen} compact />)}
              </div>
            ))}
          </div>
        )}
        {!onlyToday && (
          <div className="hidden w-40 md:block">
            <MiniMonth density={data.month_density} today={todayDate} />
          </div>
        )}
      </div>
      {open && (
        <Modal title={open.title} onClose={() => setOpen(null)}>
          <div className="space-y-2 text-sm text-ink-300">
            <p className="text-ink-200">{open.all_day ? `All day, ${formatDate(open.start)}` : `${formatDate(open.start, "EEE, MMM d")}, ${formatTime(open.start)} to ${formatTime(open.end)}`}</p>
            <p className="text-xs">
              <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: open.color }} /> {open.calendar}
              {open.tentative ? " · tentative" : ""}
            </p>
            {open.location && (
              <p className="flex items-start gap-1">
                <MapPin size={14} className="mt-0.5 shrink-0" /> {open.location}
              </p>
            )}
            {open.description && <p className="whitespace-pre-line text-xs text-ink-400">{open.description}</p>}
            {open.join_url && (
              <a href={open.join_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded bg-accent/15 px-3 py-1.5 text-accent hover:bg-accent/25">
                <ExternalLink size={14} /> Join meeting
              </a>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

export function CalendarWidget({ kiosk, onlyToday }: { kiosk?: boolean; onlyToday?: boolean }) {
  const q = useCalendar(7);
  return (
    <Card title="Calendar" envelope={q.data} error={q.error} onRetry={() => q.refetch()} kiosk={kiosk}>
      {(d) => <CalendarBody data={d} kiosk={kiosk} onlyToday={onlyToday} />}
    </Card>
  );
}
