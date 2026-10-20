import { clamp } from "../lib/format";

export function ProgressBar({ value, max = 100, className = "", color = "bg-accent", height = "h-2", label }: { value: number; max?: number; className?: string; color?: string; height?: string; label?: string }) {
  const pct = max > 0 ? clamp((value / max) * 100, 0, 100) : 0;
  return (
    <div className={`w-full overflow-hidden rounded-full bg-ink-700 ${height} ${className}`} role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className={`${height} ${color} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Three segment bar: used (solid green), pending (striped amber), remaining (gray). Values are percentages. */
export function SplitBar({ used, pending, height = "h-2.5", className = "" }: { used: number; pending: number; height?: string; className?: string }) {
  const u = clamp(used, 0, 100);
  const p = clamp(pending, 0, 100 - u);
  return (
    <div className={`flex w-full overflow-hidden rounded-full bg-ink-700 ${height} ${className}`} aria-hidden="true">
      <div className={`${height} bg-accent`} style={{ width: `${u}%` }} />
      <div className={`${height} striped`} style={{ width: `${p}%` }} />
    </div>
  );
}

export function Chip({ children, tone = "neutral", className = "" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "info"; className?: string }) {
  const tones: Record<string, string> = {
    neutral: "border-ink-600 bg-ink-800 text-ink-300",
    good: "border-accent/40 bg-accent/10 text-accent",
    warn: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    bad: "border-red-500/40 bg-red-500/10 text-red-300",
    info: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  };
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${tones[tone]} ${className}`}>{children}</span>;
}
