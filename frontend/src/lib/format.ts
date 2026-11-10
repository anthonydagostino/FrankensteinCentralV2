import { formatInTimeZone } from "date-fns-tz";
import { differenceInMinutes, isValid, parseISO } from "date-fns";

/** Every time shown in the UI is in this zone, whatever the browser's zone is. */
export const TZ = "America/New_York";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usdWhole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 0 });

/** "$1,234.56"; negative values keep a leading minus; `sign` adds a plus to positives. */
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

function parseInstant(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = parseISO(iso);
  return isValid(d) ? d : null;
}

/** Date time string to a time of day in America/New_York, for example "9:30 AM". Empty when unparseable. */
export function formatTime(iso: string | null | undefined, pattern = "h:mm a"): string {
  const d = parseInstant(iso);
  return d ? formatInTimeZone(d, TZ, pattern) : "";
}

export const formatHour = (iso: string | null | undefined) => formatTime(iso, "h a");

/** Date time string to a date in America/New_York, for example "Tue, Oct 20". */
export const formatDate = (iso: string | null | undefined, pattern = "EEE, MMM d") => formatTime(iso, pattern);

/** Calendar date string (YYYY-MM-DD) to text with no time zone shift. Empty when missing or malformed. */
export function formatDateOnly(iso: string | null | undefined, pattern = "MMM d"): string {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  // Date.UTC rolls an out of range month or day over instead of failing, so check it round trips
  if (!isValid(date) || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) return "";
  return formatInTimeZone(date, "UTC", pattern);
}

/** "just now", "5 min ago", "3 h ago", "2 d ago", or "never". */
export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  const d = parseInstant(iso);
  if (!d) return "never";
  const minutes = differenceInMinutes(now, d);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

/** Seconds to "45s", "12m", "1h 1m", or "3d 18h". */
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

/** Percentage of `part` over `whole`, clamped to 0 to 100; 0 when the whole is zero. */
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

/** "Good morning, Anthony" and friends, by the hour in America/New_York. */
export function greeting(now: Date, name: string): string {
  const hour = Number(formatInTimeZone(now, TZ, "H"));
  const part = hour < 5 ? "night" : hour < 12 ? "morning" : hour < 17 ? "afternoon" : hour < 21 ? "evening" : "night";
  return `Good ${part}, ${name}`;
}
