import { ExternalLink, Pause, Play, Tv } from "lucide-react";
import { usePlex } from "../api/hooks";
import type { PlexData, PlexItem, PlexSession } from "../api/types";
import { Chip, ProgressBar } from "../components/Bars";
import { Card } from "../components/Card";

function poster(path: string | null, w = 160, h = 240): string | null {
  if (!path) return null;
  return `/api/plex/image?path=${encodeURIComponent(path)}&w=${w}&h=${h}`;
}

function itemLink(data: PlexData, ratingKey: string): string {
  return data.links.item_template.replace("{rating_key}", ratingKey);
}

function SessionCard({ s, data, large }: { s: PlexSession; data: PlexData; large?: boolean }) {
  const img = poster(s.thumb, 120, 180);
  return (
    <a href={itemLink(data, s.rating_key)} target="_blank" rel="noreferrer" className="flex gap-3 rounded-lg bg-ink-800/60 p-2 hover:bg-ink-800">
      {img ? <img src={img} alt="" className={`${large ? "h-32 w-[86px]" : "h-24 w-16"} shrink-0 rounded object-cover`} loading="lazy" /> : <div className="h-24 w-16 rounded bg-ink-700" />}
      <div className="min-w-0 flex-1">
        <div className={`truncate ${large ? "text-lg" : "text-sm"} font-semibold text-ink-200`}>{s.title}</div>
        {s.subtitle && <div className="truncate text-xs text-ink-300">{s.subtitle}</div>}
        <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-ink-400">
          <span>{s.user}</span>
          <span>·</span>
          <span>{s.player}</span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          {s.state === "paused" ? <Pause size={12} className="text-ink-400" /> : <Play size={12} className="text-accent" />}
          <ProgressBar value={s.progress} height="h-1.5" className="flex-1" label="Progress" />
          <span className="tabular text-[11px] text-ink-400">{s.progress}%</span>
        </div>
        <div className="mt-1">
          <Chip tone={s.transcoding ? "warn" : "good"}>{s.transcoding ? "Transcoding" : "Direct Play"}</Chip>
        </div>
      </div>
    </a>
  );
}

function Rail({ title, items, data }: { title: string; items: PlexItem[]; data: PlexData }) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">{title}</div>
      <div className="scrollbar-thin flex gap-2 overflow-x-auto pb-1">
        {items.map((it) => {
          const img = poster(it.thumb, 120, 180);
          return (
            <a key={it.rating_key} href={itemLink(data, it.rating_key)} target="_blank" rel="noreferrer" className="w-20 shrink-0" title={`${it.title}${it.subtitle ? `, ${it.subtitle}` : ""}`}>
              {img ? <img src={img} alt="" className="h-[120px] w-20 rounded object-cover" loading="lazy" /> : <div className="h-[120px] w-20 rounded bg-ink-700" />}
              {it.progress !== null && it.progress > 0 && <ProgressBar value={it.progress} height="h-1" className="mt-0.5" label="Progress" />}
              <div className="mt-1 truncate text-[11px] text-ink-200">{it.title}</div>
              {it.subtitle && <div className="truncate text-[10px] text-ink-400">{it.subtitle}</div>}
            </a>
          );
        })}
      </div>
    </div>
  );
}

export function PlexBody({ data, kiosk, onlyNowPlaying }: { data: PlexData; kiosk?: boolean; onlyNowPlaying?: boolean }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-2 text-sm text-ink-300">
          <span className={`h-2.5 w-2.5 rounded-full ${data.server.online ? "bg-accent" : "bg-red-500"}`} />
          {data.server.name ?? "Plex"} {data.server.version ? `v${data.server.version.split("-")[0]}` : ""}
        </span>
        {!onlyNowPlaying && data.libraries.map((l) => (
          <Chip key={l.key}>
            {l.title}: {l.count ?? "?"}
          </Chip>
        ))}
        <a href={data.links.server} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 rounded-md bg-accent/15 px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent/25">
          <Tv size={14} /> Open Plex <ExternalLink size={12} />
        </a>
      </div>
      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Now playing</div>
        {data.sessions.length === 0 ? (
          <p className="text-sm text-ink-500">Nothing playing</p>
        ) : (
          <div className={`grid gap-2 ${kiosk ? "grid-cols-1" : "md:grid-cols-2"}`}>
            {data.sessions.map((s) => (
              <SessionCard key={s.session_key ?? s.rating_key} s={s} data={data} large={kiosk} />
            ))}
          </div>
        )}
      </div>
      {!onlyNowPlaying && (
        <>
          <Rail title="On deck" items={data.on_deck} data={data} />
          <Rail title="Recently added" items={data.recently_added} data={data} />
        </>
      )}
    </div>
  );
}

export function PlexWidget({ kiosk, onlyNowPlaying }: { kiosk?: boolean; onlyNowPlaying?: boolean }) {
  const q = usePlex();
  return (
    <Card title="Plex" envelope={q.data} error={q.error} onRetry={() => q.refetch()} kiosk={kiosk}>
      {(d) => <PlexBody data={d} kiosk={kiosk} onlyNowPlaying={onlyNowPlaying} />}
    </Card>
  );
}
