import { CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useAttention } from "../api/hooks";
import type { AttentionItem } from "../api/types";
import { DynamicIcon } from "../lib/icons";
import { usePrivacy } from "../lib/privacy";

const TONE: Record<AttentionItem["severity"], string> = {
  critical: "border-red-500/50 bg-red-500/10 text-red-100",
  warning: "border-amber-500/50 bg-amber-500/10 text-amber-100",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-100",
};

function Item({ item, large }: { item: AttentionItem; large?: boolean }) {
  const { blurred } = usePrivacy();
  const blur = blurred && item.source === "benefits" ? "privacy-blur" : "";
  const inner = (
    <>
      <DynamicIcon name={item.icon} size={large ? 20 : 16} className="shrink-0" />
      <span className="min-w-0">
        <span className={`block truncate font-medium ${large ? "text-base" : "text-sm"} ${blur}`}>{item.title}</span>
        {item.detail && <span className={`block truncate ${large ? "text-sm" : "text-[11px]"} opacity-80`}>{item.detail}</span>}
      </span>
    </>
  );
  const cls = `flex min-w-0 max-w-full items-center gap-2 rounded-lg border px-3 py-1.5 ${TONE[item.severity]}`;
  if (item.link && item.link.startsWith("/")) {
    return (
      <Link to={item.link} className={`${cls} hover:brightness-110`}>
        {inner}
      </Link>
    );
  }
  if (item.link) {
    return (
      <a href={item.link} target="_blank" rel="noreferrer" className={`${cls} hover:brightness-110`}>
        {inner}
      </a>
    );
  }
  return <div className={cls}>{inner}</div>;
}

export function AttentionStrip({ location, large }: { location?: string; large?: boolean }) {
  const q = useAttention(location);
  const items = q.data?.data?.items ?? [];
  if (q.isLoading) {
    return <div className="h-9 animate-pulse-soft rounded-lg bg-ink-800/70" />;
  }
  if (items.length === 0) {
    return (
      <div className={`inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3 py-1 ${large ? "text-base" : "text-sm"} text-accent`}>
        <CheckCircle2 size={large ? 18 : 15} /> All clear
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2" aria-label="Attention">
      {items.map((item, i) => (
        <Item key={`${item.source}-${i}`} item={item} large={large} />
      ))}
    </div>
  );
}
