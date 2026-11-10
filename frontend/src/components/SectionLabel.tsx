import type { ReactNode } from "react";

/** The small uppercase heading used above every list or chart inside a card. */
export function SectionLabel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400 ${className}`}>{children}</div>;
}

/** Shared Recharts tooltip styling so every chart matches the card theme. */
export const TOOLTIP_STYLE = { background: "#171e1a", border: "1px solid #2f3a33", fontSize: 12 } as const;

/** Border, background, and radius shared by every card and page panel. */
export const PANEL_CLASS = "rounded-xl border border-ink-700 bg-ink-900/80";

/** Severity to color classes, shared by the attention strip and weather alert banners. */
export const SEVERITY_CLASS = {
  critical: "border-red-500/50 bg-red-500/10 text-red-100",
  warning: "border-amber-500/50 bg-amber-500/10 text-amber-100",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-100",
} as const;
