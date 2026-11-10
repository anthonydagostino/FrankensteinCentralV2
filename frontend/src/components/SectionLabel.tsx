import type { ReactNode } from "react";

/** The small uppercase heading used above every list or chart inside a card. */
export function SectionLabel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400 ${className}`}>{children}</div>;
}
