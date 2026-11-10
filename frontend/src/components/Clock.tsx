import { formatInTimeZone } from "date-fns-tz";
import { TZ } from "../lib/format";
import { useNow } from "../lib/useNow";

/** Live clock in America/New_York. The large variant adds seconds for the kiosk. */
export function Clock({ large = false }: { large?: boolean }) {
  const now = useNow(1000);
  const [time, ampm, seconds, day] = formatInTimeZone(now, TZ, large ? "h:mm|a|ss|EEEE, MMMM d, yyyy" : "h:mm|a||EEE, MMM d, yyyy").split("|");
  return (
    <div className={`tabular ${large ? "text-right" : ""}`}>
      <div className={`${large ? "text-6xl" : "text-lg"} font-semibold leading-none text-ink-200`}>
        {time}
        <span className={`${large ? "text-3xl" : "text-xs"} ml-1 text-ink-400`}>{ampm}</span>
        {large && <span className="ml-3 text-2xl text-ink-400">{seconds}</span>}
      </div>
      <div className={`${large ? "mt-2 text-xl" : "text-[11px]"} text-ink-400`}>{day}</div>
    </div>
  );
}
