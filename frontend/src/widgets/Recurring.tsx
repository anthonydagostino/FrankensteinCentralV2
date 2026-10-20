import { ArrowUpRight, ChevronDown, EyeOff, RotateCcw } from "lucide-react";
import { useState } from "react";
import { useRecurring, useRecurringIgnore } from "../api/hooks";
import type { RecurringData, RecurringItem } from "../api/types";
import { Chip } from "../components/Bars";
import { Card } from "../components/Card";
import { Money } from "../components/Money";
import { formatDateOnly } from "../lib/format";

const CADENCE_LABEL: Record<RecurringItem["cadence"], string> = { weekly: "weekly", biweekly: "every 2 weeks", monthly: "monthly", bimonthly: "every 2 months", quarterly: "quarterly", semiannual: "twice a year", annual: "yearly" };

function dueLabel(item: RecurringItem): string {
  if (item.status === "lapsed") return `last seen ${formatDateOnly(item.last_seen)}`;
  if (item.days_until_next < 0) return `expected ${formatDateOnly(item.next_expected)}, not seen yet`;
  if (item.days_until_next === 0) return "due today";
  if (item.days_until_next === 1) return "due tomorrow";
  return `due in ${item.days_until_next} days`;
}

function Row({ item, readOnly }: { item: RecurringItem; readOnly: boolean }) {
  const ignore = useRecurringIgnore();
  return (
    <li className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded px-2 py-1.5 text-sm hover:bg-ink-800/70 ${item.ignored ? "opacity-50" : ""}`}>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-1.5">
          {item.url ? (
            <a href={item.url} target="_blank" rel="noreferrer" className="truncate text-ink-200 hover:underline" title={item.name}>
              {item.name}
            </a>
          ) : (
            <span className="truncate text-ink-200">{item.name}</span>
          )}
          {item.price_increase && (
            <Chip tone="warn">
              <ArrowUpRight size={11} /> was <Money value={item.previous_amount} />
            </Chip>
          )}
          {item.new && <Chip tone="info">new</Chip>}
          {item.status === "lapsed" && <Chip tone="neutral">stopped</Chip>}
          {item.variable && <Chip tone="neutral">varies</Chip>}
          {item.passthrough && <Chip tone="neutral">via processor</Chip>}
        </span>
        <span className="block truncate text-[11px] text-ink-400">
          {CADENCE_LABEL[item.cadence]} · {item.account} · {dueLabel(item)}
          {item.category ? ` · ${item.category}` : ""}
        </span>
      </span>
      <span className="text-right">
        <span className="block text-ink-200">
          <Money value={item.amount} />
          {item.variable && <span className="text-[11px] text-ink-400"> (<Money value={item.amount_min} /> to <Money value={item.amount_max} />)</span>}
        </span>
        <span className="block text-[11px] text-ink-400">
          <Money value={item.annual_cost} /> / yr
        </span>
      </span>
      {!readOnly && (
        <button
          type="button"
          onClick={() => ignore.mutate({ key: item.key, ignore: !item.ignored })}
          className="rounded p-1 text-ink-400 hover:bg-ink-700 hover:text-ink-200"
          title={item.ignored ? "Show again" : "Ignore this charge"}
          aria-label={item.ignored ? "Show again" : "Ignore this charge"}
        >
          {item.ignored ? <RotateCcw size={13} /> : <EyeOff size={13} />}
        </button>
      )}
    </li>
  );
}

export function RecurringBody({ data, readOnly }: { data: RecurringData; readOnly: boolean }) {
  const [showAll, setShowAll] = useState(false);
  const t = data.totals;
  const active = data.items.filter((i) => i.status === "active" && !i.ignored);
  const rest = data.items.filter((i) => i.status === "lapsed" || i.ignored);
  const needsAttention = active.filter((i) => i.price_increase || i.new);
  const others = active.filter((i) => !i.price_increase && !i.new);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="good">
          <Money value={t.monthly_total} /> / month
        </Chip>
        <Chip>
          <Money value={t.annual_total} /> / year
        </Chip>
        <Chip>{t.active_count} active</Chip>
        {t.increased_count > 0 && <Chip tone="warn">{t.increased_count} price increase{t.increased_count > 1 ? "s" : ""}</Chip>}
        {t.new_count > 0 && <Chip tone="info">{t.new_count} new</Chip>}
        {t.lapsed_count > 0 && <Chip>{t.lapsed_count} stopped</Chip>}
      </div>
      <p className="text-[11px] text-ink-400">Charges that repeat on a schedule, found by clustering Firefly withdrawals by merchant and cadence over the last year. Transfers never count. Ignore anything that is not a subscription.</p>
      {data.items.length === 0 && <p className="text-sm text-ink-500">No recurring charges found yet</p>}
      {needsAttention.length > 0 && (
        <ul className="divide-y divide-ink-800 rounded-lg border border-amber-500/30 bg-amber-500/5">
          {needsAttention.map((i) => (
            <Row key={i.key} item={i} readOnly={readOnly} />
          ))}
        </ul>
      )}
      <ul className="divide-y divide-ink-800">
        {others.map((i) => (
          <Row key={i.key} item={i} readOnly={readOnly} />
        ))}
      </ul>
      {rest.length > 0 && (
        <>
          <button type="button" onClick={() => setShowAll(!showAll)} className="inline-flex items-center gap-1 text-[11px] text-ink-400 hover:text-ink-200" aria-expanded={showAll}>
            <ChevronDown size={12} className={showAll ? "rotate-180" : ""} /> {rest.length} stopped or ignored
          </button>
          {showAll && (
            <ul className="divide-y divide-ink-800">
              {rest.map((i) => (
                <Row key={i.key} item={i} readOnly={readOnly} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

export function RecurringWidget({ readOnly }: { readOnly: boolean }) {
  const q = useRecurring();
  return (
    <Card title="Recurring charges" envelope={q.data} error={q.error} onRetry={() => q.refetch()}>
      {(d) => <RecurringBody data={d} readOnly={readOnly} />}
    </Card>
  );
}
