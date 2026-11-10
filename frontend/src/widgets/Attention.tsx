import { CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useAttention } from "../api/hooks";
import type { AttentionItem } from "../api/types";
import { SEVERITY_CLASS } from "../lib/ui";
import { DynamicIcon } from "../lib/icons";
import { usePrivacy } from "../lib/privacyContext";

/** Sources whose titles and details carry dollar amounts, so the privacy blur must cover them. */
const MONEY_SOURCES = new Set(["benefits", "recurring", "finance"]);

function Item({ item, large }: { item: AttentionItem; large?: boolean }) {
  const { blurred } = usePrivacy();
  const blur = blurred && MONEY_SOURCES.has(item.source) ? "privacy-blur" : "";
  const inner = (
    <>
      <DynamicIcon name={item.icon} size={large ? 20 : 16} className="shrink-0" />
      <span className="min-w-0">
        <span className={`block truncate font-medium ${large ? "text-base" : "text-sm"} ${blur}`}>{item.title}</span>
        {item.detail && <span className={`block truncate ${large ? "text-sm" : "text-[11px]"} opacity-80 ${blur}`}>{item.detail}</span>}
      </span>
    </>
  );
  const cls = `flex min-w-0 max-w-full items-center gap-2 rounded-lg border px-3 py-1.5 ${SEVERITY_CLASS[item.severity]}`;
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
      <div
        className={`inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3 py-1 ${large ? "text-base" : "text-sm"} text-accent`}
      >
        <CheckCircle2 size={large ? 18 : 15} /> All clear
      </div>
    );
  }
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Attention">
      {items.map((item) => (
        <li key={`${item.source}:${item.title}`} className="min-w-0 max-w-full">
          <Item item={item} large={large} />
        </li>
      ))}
    </ul>
  );
}
