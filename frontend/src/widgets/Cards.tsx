import { CreditCard } from "lucide-react";
import { useCards } from "../api/hooks";
import type { CardData } from "../api/types";
import { Card } from "../components/Card";
import { FeeOffset } from "../components/FeeOffset";
import { Money } from "../components/Money";
import { formatDateOnly } from "../lib/format";

function CardTile({ c }: { c: CardData }) {
  if (!c.configured) {
    return (
      <div className="rounded-lg border border-dashed border-ink-600 p-3 text-xs text-ink-400">
        <div className="font-medium text-ink-200">{c.label}</div>
        {c.message}
      </div>
    );
  }
  return (
    <div className="rounded-lg bg-ink-800/60 p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CreditCard size={16} className="text-ink-300" />
          <span className="text-sm font-semibold text-ink-200">{c.label}</span>
        </div>
        {c.url ? (
          <a href={c.url} target="_blank" rel="noreferrer" className="text-[11px] text-ink-400 hover:text-ink-200">
            {c.account?.name}
          </a>
        ) : (
          <span className="text-[11px] text-ink-400">{c.account?.name}</span>
        )}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div className="text-ink-400">Balance</div>
        <div className="text-right text-ink-200">
          <Money value={c.balance} href={c.url} />
        </div>
        <div className="text-ink-400">Spent this month</div>
        <div className="text-right text-ink-200">
          <Money value={c.spend_month} />
        </div>
        <div className="text-ink-400">Last 30 days</div>
        <div className="text-right text-ink-200">
          <Money value={c.spend_30d} />
        </div>
        {c.largest_purchase && (
          <>
            <div className="text-ink-400">Largest purchase</div>
            <div className="truncate text-right text-ink-200" title={c.largest_purchase.description}>
              <Money value={c.largest_purchase.amount} /> <span className="text-ink-400">{c.largest_purchase.description}</span>
            </div>
          </>
        )}
        {c.last_credit && (
          <>
            <div className="text-ink-400">Last credit</div>
            <div className="truncate text-right text-accent" title={c.last_credit.description}>
              <Money value={c.last_credit.amount} /> <span className="text-ink-400">{formatDateOnly(c.last_credit.date)}</span>
            </div>
          </>
        )}
        {c.credit_limit && (
          <>
            <div className="text-ink-400">Limit set in Firefly</div>
            <div className="text-right text-ink-400">
              <Money value={c.credit_limit} />
            </div>
          </>
        )}
      </div>
      <FeeOffset captured={c.captured_ytd} fee={c.annual_fee} offset={c.fee_offset} className="mt-3" />
    </div>
  );
}

export function CardsWidget() {
  const q = useCards();
  return (
    <Card title="Amex cards" envelope={q.data} error={q.error} onRetry={() => q.refetch()}>
      {(d) => (
        <div className="space-y-3">
          {d.cards.map((c) => (
            <CardTile key={c.id} c={c} />
          ))}
        </div>
      )}
    </Card>
  );
}
