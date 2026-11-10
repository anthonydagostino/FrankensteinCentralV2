import { ProgressBar } from "./Bars";
import { Money } from "./Money";

/** "Captured of fee (percent)" line with its progress bar; green once the fee is covered. */
export function FeeOffset({
  captured,
  fee,
  offset,
  className = "",
}: {
  captured: string | undefined;
  fee: string;
  offset: number | null | undefined;
  className?: string;
}) {
  const ratio = offset ?? 0;
  return (
    <div className={className}>
      <div className="flex justify-between text-[11px]">
        <span className="text-ink-400">Fee offset</span>
        <span className="text-ink-200">
          <Money value={captured} /> of <Money value={fee} /> ({Math.round(ratio * 100)}%)
        </span>
      </div>
      <ProgressBar value={ratio * 100} color={ratio >= 1 ? "bg-accent" : "bg-sky-400"} className="mt-1" label="Fee offset" />
    </div>
  );
}
