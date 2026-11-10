import { AlertCircle, RefreshCw, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import type { Envelope, ModuleStatus } from "../api/types";
import { formatTime, relativeTime } from "../lib/format";
import { useNow } from "../lib/useNow";
import { ErrorBoundary } from "./ErrorBoundary";
import { PANEL_CLASS } from "../lib/ui";

export function StatusDot({ status, stale }: { status: ModuleStatus | "loading"; stale?: boolean }) {
  const color = stale
    ? "bg-amber-400"
    : status === "ok"
      ? "bg-accent"
      : status === "degraded"
        ? "bg-amber-400"
        : status === "disabled"
          ? "bg-ink-400"
          : status === "loading"
            ? "bg-ink-400 animate-pulse-soft"
            : "bg-red-500";
  return <span className={`inline-block h-2 w-2 rounded-full ${color}`} aria-label={stale ? `${status}, stale` : status} />;
}

export function StaleBadge({ fetchedAt, now }: { fetchedAt: string | null; now: Date }) {
  return (
    <span
      className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300"
      title={fetchedAt ? `Last update ${formatTime(fetchedAt, "MMM d, h:mm a")}` : "No data yet"}
    >
      stale, {relativeTime(fetchedAt, now)}
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse-soft rounded bg-ink-700/70 ${className}`} />;
}

/** The "not configured" card: which env vars would turn the integration on. */
export function SetupHint({ title, vars, message }: { title: string; vars?: string[] | null; message?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-ink-600 bg-ink-800/40 p-4 text-sm text-ink-300">
      <p className="font-medium text-ink-200">{title} is not configured</p>
      <p className="mt-1">{message ?? "Set these variables in .env and restart the container:"}</p>
      {vars && vars.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-2">
          {vars.map((v) => (
            <li key={v}>
              <code className="rounded bg-ink-900 px-2 py-0.5 font-mono text-xs text-accent">{v}</code>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
      <AlertCircle size={16} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="break-words">{message ?? "Something went wrong"}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 inline-flex items-center gap-1 rounded border border-red-400/40 px-2 py-1 text-xs hover:bg-red-500/20"
          >
            <RefreshCw size={12} /> Retry
          </button>
        )}
      </div>
    </div>
  );
}

const FIRST_REFRESH = "First refresh has not completed yet";

interface CardProps<T> {
  title: string;
  icon?: ReactNode;
  envelope?: Envelope<T>;
  /** Client-side fetch error from TanStack Query (the backend itself was unreachable). */
  error?: Error | null;
  onRetry?: () => void;
  actions?: ReactNode;
  className?: string;
  children: (data: T, envelope: Envelope<T>) => ReactNode;
  /** Larger header, no footer, and no per-card clock on the always-on display. */
  kiosk?: boolean;
}

/**
 * The frame every widget renders in. Picks the body from the envelope: waiting skeleton, setup hint
 * (disabled), error with retry (no data), or the widget content with degraded, error, and stale notices.
 */
export function Card<T>({ title, icon, envelope, error, onRetry, actions, className = "", children, kiosk }: CardProps<T>) {
  const now = useNow(kiosk ? 0 : 30_000);
  const status: ModuleStatus | "loading" = envelope ? envelope.status : "loading";
  const waiting = !!envelope && envelope.data === null && envelope.error === FIRST_REFRESH;
  let body: ReactNode;
  if (error && !envelope) {
    body = <ErrorState message={error.message} onRetry={onRetry} />;
  } else if (!envelope || waiting) {
    body = (
      <div className="space-y-2" aria-busy="true">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  } else if (envelope.status === "disabled") {
    body = <SetupHint title={title} vars={envelope.setup_hint} />;
  } else if (envelope.data === null) {
    body = <ErrorState message={envelope.error} onRetry={onRetry} />;
  } else {
    const notice = error
      ? { tone: "bad", icon: <WifiOff size={12} />, text: `Dashboard unreachable: ${error.message}` }
      : envelope.status === "error" && envelope.error
        ? { tone: "bad", icon: <AlertCircle size={12} />, text: envelope.error }
        : envelope.status === "degraded" && envelope.error
          ? { tone: "warn", icon: <AlertCircle size={12} />, text: `Partial data: ${envelope.error}` }
          : null;
    body = (
      <>
        {notice && (
          <div
            className={`mb-3 flex items-center gap-2 rounded border px-2 py-1 text-xs ${notice.tone === "bad" ? "border-red-500/30 bg-red-500/10 text-red-200" : "border-amber-500/30 bg-amber-500/10 text-amber-200"}`}
            title={notice.text}
          >
            {notice.icon} <span className="truncate">{notice.text}</span>
            {onRetry && (
              <button type="button" onClick={onRetry} className="ml-auto underline">
                retry
              </button>
            )}
          </div>
        )}
        <ErrorBoundary name={title}>{children(envelope.data as T, envelope)}</ErrorBoundary>
      </>
    );
  }
  return (
    <section className={`flex min-w-0 flex-col ${PANEL_CLASS} shadow-sm ${className}`} aria-label={title}>
      <header className={`flex items-center gap-2 border-b border-ink-700/70 px-4 ${kiosk ? "py-3" : "py-2.5"}`}>
        <StatusDot status={status} stale={envelope?.stale} />
        {icon && <span className="text-ink-300">{icon}</span>}
        <h2 className={`${kiosk ? "text-lg" : "text-sm"} font-semibold tracking-wide text-ink-200`}>{title}</h2>
        {envelope?.stale && <StaleBadge fetchedAt={envelope.fetched_at} now={now} />}
        <div className="ml-auto flex items-center gap-2">{actions}</div>
      </header>
      <div className="min-w-0 flex-1 p-4">{body}</div>
      {!kiosk && (
        <footer className="px-4 pb-2 text-[11px] text-ink-400">
          {envelope?.fetched_at
            ? `Updated ${relativeTime(envelope.fetched_at, now)}`
            : envelope?.status === "disabled"
              ? "Not configured"
              : "Waiting for first refresh"}
        </footer>
      )}
    </section>
  );
}
