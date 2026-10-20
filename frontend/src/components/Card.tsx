import { AlertCircle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import type { Envelope, ModuleStatus } from "../api/types";
import { relativeTime } from "../lib/format";
import { useNow } from "./Clock";

export function StatusDot({ status, stale, className = "" }: { status: ModuleStatus | "loading"; stale?: boolean; className?: string }) {
  const color = stale ? "bg-amber-400" : status === "ok" ? "bg-accent" : status === "degraded" ? "bg-amber-400" : status === "disabled" ? "bg-ink-400" : status === "loading" ? "bg-ink-400 animate-pulse-soft" : "bg-red-500";
  return <span className={`inline-block h-2 w-2 rounded-full ${color} ${className}`} aria-label={status} />;
}

export function StaleBadge({ fetchedAt }: { fetchedAt: string | null }) {
  const now = useNow(30_000);
  return (
    <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300" title={fetchedAt ? `Last update ${new Date(fetchedAt).toLocaleString()}` : "No data yet"}>
      stale, {relativeTime(fetchedAt, now)}
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse-soft rounded bg-ink-700/70 ${className}`} />;
}

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

export function ErrorState({ message, onRetry, children }: { message: string | null; onRetry?: () => void; children?: ReactNode }) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
        <AlertCircle size={16} className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="break-words">{message ?? "Something went wrong"}</p>
          {onRetry && (
            <button type="button" onClick={onRetry} className="mt-2 inline-flex items-center gap-1 rounded border border-red-400/40 px-2 py-1 text-xs hover:bg-red-500/20">
              <RefreshCw size={12} /> Retry
            </button>
          )}
        </div>
      </div>
      {children}
    </div>
  );
}

export interface CardProps<T> {
  title: string;
  icon?: ReactNode;
  envelope?: Envelope<T>;
  loading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  skeleton?: ReactNode;
  children: (data: T, envelope: Envelope<T>) => ReactNode;
  kiosk?: boolean;
}

export function Card<T>({ title, icon, envelope, loading, error, onRetry, actions, className = "", bodyClassName = "", skeleton, children, kiosk }: CardProps<T>) {
  const now = useNow(30_000);
  const status: ModuleStatus | "loading" = envelope ? envelope.status : "loading";
  const isLoading = loading || (!envelope && !error);
  let body: ReactNode;
  if (error && !envelope) {
    body = <ErrorState message={error.message} onRetry={onRetry} />;
  } else if (isLoading) {
    body = skeleton ?? (
      <div className="space-y-2">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  } else if (envelope && envelope.status === "disabled") {
    body = <SetupHint title={title} vars={envelope.setup_hint} />;
  } else if (envelope && envelope.data === null) {
    body = <ErrorState message={envelope.error ?? "No data yet"} onRetry={onRetry} />;
  } else if (envelope) {
    body = (
      <>
        {envelope.status === "error" && envelope.error && (
          <div className="mb-3 flex items-center gap-2 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-xs text-red-200">
            <AlertCircle size={12} /> <span className="truncate">{envelope.error}</span>
            {onRetry && (
              <button type="button" onClick={onRetry} className="ml-auto underline">
                retry
              </button>
            )}
          </div>
        )}
        {envelope.status === "degraded" && envelope.error && (
          <div className="mb-3 truncate rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-200" title={envelope.error}>
            Partial data: {envelope.error}
          </div>
        )}
        {children(envelope.data as T, envelope)}
      </>
    );
  }
  return (
    <section className={`flex min-w-0 flex-col rounded-xl border border-ink-700 bg-ink-900/80 shadow-sm ${className}`} aria-label={title}>
      <header className={`flex items-center gap-2 border-b border-ink-700/70 px-4 ${kiosk ? "py-3" : "py-2.5"}`}>
        <StatusDot status={status} stale={envelope?.stale} />
        {icon && <span className="text-ink-300">{icon}</span>}
        <h2 className={`${kiosk ? "text-lg" : "text-sm"} font-semibold tracking-wide text-ink-200`}>{title}</h2>
        {envelope?.stale && <StaleBadge fetchedAt={envelope.fetched_at} />}
        <div className="ml-auto flex items-center gap-2">{actions}</div>
      </header>
      <div className={`min-w-0 flex-1 p-4 ${bodyClassName}`}>{body}</div>
      {!kiosk && (
        <footer className="px-4 pb-2 text-[11px] text-ink-400">{envelope?.fetched_at ? `Updated ${relativeTime(envelope.fetched_at, now)}` : envelope?.status === "disabled" ? "Not configured" : "Waiting for first refresh"}</footer>
      )}
    </section>
  );
}
