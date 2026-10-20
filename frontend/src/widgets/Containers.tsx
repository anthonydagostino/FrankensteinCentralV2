import { ExternalLink, RotateCw, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useContainers, useRestartContainer } from "../api/hooks";
import type { ContainerRow, ContainersData } from "../api/types";
import { Chip } from "../components/Bars";
import { Card } from "../components/Card";
import { humanDuration } from "../lib/format";

const STATE_COLOR: Record<string, string> = { running: "bg-accent", restarting: "bg-amber-400", paused: "bg-sky-400", exited: "bg-red-500", dead: "bg-red-600", created: "bg-ink-400" };

function isProblem(c: ContainerRow): boolean {
  return c.state !== "running" || c.health === "unhealthy" || c.restart_increased;
}

function Row({ c, allowRestart, readOnly }: { c: ContainerRow; allowRestart: boolean; readOnly: boolean }) {
  const restart = useRestartContainer();
  const [confirm, setConfirm] = useState(false);
  const tag = c.image?.includes(":") ? c.image.split(":").pop() : c.image;
  return (
    <li className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-ink-800/70">
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATE_COLOR[c.state] ?? "bg-ink-400"}`} title={c.state} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          {c.url ? (
            <a href={c.url} target="_blank" rel="noreferrer" className="truncate text-ink-200 hover:underline">
              {c.display_name}
            </a>
          ) : (
            <span className="truncate text-ink-200">{c.display_name}</span>
          )}
          {c.critical && <Chip tone="info">critical</Chip>}
        </span>
        <span className="block truncate text-[11px] text-ink-400" title={c.image ?? ""}>
          {tag} · {c.state === "running" && c.uptime_seconds !== null ? `up ${humanDuration(c.uptime_seconds)}` : c.status}
        </span>
      </span>
      {c.health !== "none" && <Chip tone={c.health === "healthy" ? "good" : c.health === "unhealthy" ? "bad" : "warn"}>{c.health}</Chip>}
      {c.restart_count !== null && c.restart_count > 0 && (
        <span className={`tabular text-[11px] ${c.restart_increased ? "text-amber-300" : "text-ink-400"}`} title="Restart count">
          <RotateCw size={10} className="mr-0.5 inline" />
          {c.restart_count}
        </span>
      )}
      {allowRestart && !readOnly && (
        confirm ? (
          <span className="flex items-center gap-1 text-[11px]">
            <button type="button" className="rounded bg-red-500/20 px-2 py-0.5 text-red-200" onClick={() => { restart.mutate(c.id); setConfirm(false); }}>
              Confirm
            </button>
            <button type="button" className="text-ink-400" onClick={() => setConfirm(false)}>
              Cancel
            </button>
          </span>
        ) : (
          <button type="button" className="rounded p-1 text-ink-400 hover:bg-ink-700 hover:text-ink-200" title="Restart container" onClick={() => setConfirm(true)}>
            <RotateCw size={13} />
          </button>
        )
      )}
    </li>
  );
}

export function ContainersBody({ data, readOnly, summaryOnly }: { data: ContainersData; readOnly: boolean; summaryOnly?: boolean }) {
  const [filter, setFilter] = useState("");
  const [problemsOnly, setProblemsOnly] = useState(false);
  const groups = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return data.groups
      .map((g) => ({ ...g, containers: g.containers.filter((c) => (!f || c.display_name.toLowerCase().includes(f) || (c.image ?? "").toLowerCase().includes(f)) && (!problemsOnly || isProblem(c))) }))
      .filter((g) => g.containers.length > 0);
  }, [data.groups, filter, problemsOnly]);
  const s = data.summary;
  const problems = data.groups.flatMap((g) => g.containers).filter(isProblem);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="good">{s.running} running</Chip>
        <Chip tone={s.stopped ? "bad" : "neutral"}>{s.stopped} stopped</Chip>
        {s.restarting > 0 && <Chip tone="warn">{s.restarting} restarting</Chip>}
        <Chip tone={s.unhealthy ? "bad" : "neutral"}>{s.unhealthy} unhealthy</Chip>
        {s.server_version && <Chip>Docker {s.server_version}</Chip>}
        {!summaryOnly && (
          <>
            <label className="ml-auto inline-flex items-center gap-1 rounded border border-ink-700 bg-ink-800 px-2 py-1 text-xs text-ink-300">
              <Search size={12} />
              <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter" className="w-28 bg-transparent outline-none placeholder:text-ink-500" aria-label="Filter containers" />
            </label>
            <label className="inline-flex items-center gap-1 text-xs text-ink-300">
              <input type="checkbox" checked={problemsOnly} onChange={(e) => setProblemsOnly(e.target.checked)} className="accent-[#4ade80]" /> problems only
            </label>
            {data.portainer_url && (
              <a href={data.portainer_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-ink-400 hover:text-ink-200">
                Portainer <ExternalLink size={11} />
              </a>
            )}
          </>
        )}
      </div>
      {summaryOnly ? (
        problems.length > 0 ? (
          <ul className="space-y-1">
            {problems.map((c) => (
              <Row key={c.id} c={c} allowRestart={false} readOnly />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-500">All containers healthy</p>
        )
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {groups.map((g) => (
            <div key={g.project} className="rounded-lg bg-ink-800/40 p-2">
              <div className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide text-ink-400">{g.project}</div>
              <ul className="space-y-0.5">
                {g.containers.map((c) => (
                  <Row key={c.id} c={c} allowRestart={data.restart_allowed} readOnly={readOnly} />
                ))}
              </ul>
            </div>
          ))}
          {groups.length === 0 && <p className="text-sm text-ink-500">No containers match</p>}
        </div>
      )}
    </div>
  );
}

export function ContainersWidget({ readOnly, kiosk, summaryOnly }: { readOnly: boolean; kiosk?: boolean; summaryOnly?: boolean }) {
  const q = useContainers();
  return (
    <Card title="Containers" envelope={q.data} error={q.error} onRetry={() => q.refetch()} kiosk={kiosk}>
      {(d) => <ContainersBody data={d} readOnly={readOnly} summaryOnly={summaryOnly} />}
    </Card>
  );
}
