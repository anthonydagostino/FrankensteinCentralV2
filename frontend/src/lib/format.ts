import { formatInTimeZone } from "date-fns-tz";
import { differenceInMinutes, parseISO } from "date-fns";

export const TZ = "America/New_York";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usdWhole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 0 });

export function formatMoney(value: string | number | null | undefined, opts: { whole?: boolean; sign?: boolean } = {}): string {
  if (value === null || value === undefined || value === "") return "";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  const text = opts.whole ? usdWhole.format(Math.abs(n)) : usd.format(Math.abs(n));
  if (n < 0) return `-${text}`;
  if (opts.sign && n > 0) return `+${text}`;
  return text;
}

export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isNaN(n) ? 0 : n;
}

export function formatTime(iso: string | null | undefined, tz = TZ): string {
  if (!iso) return "";
  try {
    return formatInTimeZone(parseISO(iso), tz, "h:mm a");
  } catch {
    return "";
  }
}

export function formatHour(iso: string | null | undefined, tz = TZ): string {
  if (!iso) return "";
  try {
    return formatInTimeZone(parseISO(iso), tz, "h a");
  } catch {
    return "";
  }
}

export function formatDate(iso: string | null | undefined, pattern = "EEE, MMM d", tz = TZ): string {
  if (!iso) return "";
  try {
    const d = iso.length === 10 ? parseISO(`${iso}T12:00:00`) : parseISO(iso);
    return iso.length === 10 ? formatInTimeZone(d, "UTC", pattern) : formatInTimeZone(d, tz, pattern);
  } catch {
    return iso;
  }
}

export function formatDateOnly(iso: string, pattern = "MMM d"): string {
  // iso is YYYY-MM-DD; format without timezone shifts
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  return formatInTimeZone(date, "UTC", pattern);
}

export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "never";
  const minutes = differenceInMinutes(now, parseISO(iso));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

export function humanDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds < 0) return "";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ${minutes % 60}m`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

export function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

export function pct(part: string | number, whole: string | number): number {
  const w = toNumber(whole);
  if (w <= 0) return 0;
  return clamp((toNumber(part) / w) * 100, 0, 100);
}

export function minutesLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}
