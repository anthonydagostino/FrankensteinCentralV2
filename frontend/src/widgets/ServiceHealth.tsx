import { useProbes } from "../api/hooks";
import { StatusDot } from "../components/Card";

export function ServiceHealthRow() {
  const q = useProbes();
  const env = q.data;
  if (!env || env.status === "disabled" || !env.data) {
    return <div className="rounded-xl border border-ink-700 bg-ink-900/80 px-4 py-2 text-xs text-ink-500">{env?.status === "disabled" ? "No health probes configured" : "Probing services"}</div>;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-ink-700 bg-ink-900/80 px-3 py-2" aria-label="Service health">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Services</span>
      {env.data.probes.map((p) => {
        const content = (
          <>
            <StatusDot status={p.ok ? "ok" : "error"} />
            <span className="text-ink-200">{p.name}</span>
            <span className="tabular text-ink-400">{p.ok && p.latency_ms !== null ? `${p.latency_ms} ms` : p.error ?? "down"}</span>
          </>
        );
        const cls = "inline-flex items-center gap-1.5 rounded-full border border-ink-700 bg-ink-800 px-2.5 py-1 text-xs";
        return p.url ? (
          <a key={p.name} href={p.url} target="_blank" rel="noreferrer" className={`${cls} hover:border-accent/50`}>
            {content}
          </a>
        ) : (
          <span key={p.name} className={cls}>
            {content}
          </span>
        );
      })}
      {env.stale && <span className="text-[11px] text-amber-300">stale</span>}
    </div>
  );
}
