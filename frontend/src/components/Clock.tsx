import { useEffect, useState } from "react";
import { formatInTimeZone } from "date-fns-tz";
import { TZ } from "../lib/format";

export function useNow(intervalMs = 1000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

export function greeting(now: Date, name: string): string {
  const hour = Number(formatInTimeZone(now, TZ, "H"));
  const part = hour < 5 ? "night" : hour < 12 ? "morning" : hour < 17 ? "afternoon" : hour < 21 ? "evening" : "night";
  return `Good ${part}, ${name}`;
}

export function Clock({ large = false }: { large?: boolean }) {
  const now = useNow(1000);
  return (
    <div className={`tabular ${large ? "text-right" : ""}`}>
      <div className={`${large ? "text-6xl" : "text-lg"} font-semibold leading-none text-ink-200`}>{formatInTimeZone(now, TZ, "h:mm")}<span className={`${large ? "text-3xl" : "text-xs"} ml-1 text-ink-400`}>{formatInTimeZone(now, TZ, "a")}</span>{large && <span className="ml-3 text-2xl text-ink-400">{formatInTimeZone(now, TZ, "ss")}</span>}</div>
      <div className={`${large ? "mt-2 text-xl" : "text-[11px]"} text-ink-400`}>{formatInTimeZone(now, TZ, large ? "EEEE, MMMM d, yyyy" : "EEE, MMM d, yyyy")}</div>
    </div>
  );
}
