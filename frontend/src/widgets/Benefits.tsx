import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useBenefits } from "../api/hooks";
import type { BenefitCard, BenefitOut, BenefitStatus, BenefitsData } from "../api/types";
import { Chip, SplitBar, type ChipTone } from "../components/Bars";
import { Card } from "../components/Card";
import { FeeOffset } from "../components/FeeOffset";
import { Money } from "../components/Money";
import { pct, toNumber } from "../lib/format";

const STATUS_ORDER: Record<BenefitStatus, number> = { pending: 1, unused: 2, manual: 2, partial: 3, used: 4, expired_unused: 5, expired_partial: 5 };
const STATUS_LABEL: Record<BenefitStatus, string> = { used: "Used", partial: "Partial", pending: "Pending", unused: "Unused", expired_unused: "Expired", expired_partial: "Expired, partial", manual: "Mark by hand" };

/** Expiring soon first, then pending, unused, partial, used; ties broken by the larger remaining amount. */
export function sortBenefits(list: BenefitOut[]): BenefitOut[] {
  return [...list].sort((a, b) => {
    const ca = a.current;
    const cb = b.current;
    if (!ca && !cb) return 0;
    if (!ca) return 1;
    if (!cb) return -1;
    if (ca.expiring_soon !== cb.expiring_soon) return ca.expiring_soon ? -1 : 1;
    if (STATUS_ORDER[ca.status] !== STATUS_ORDER[cb.status]) return STATUS_ORDER[ca.status] - STATUS_ORDER[cb.status];
    return toNumber(cb.remaining) - toNumber(ca.remaining);
  });
}

export function statusTone(status: BenefitStatus): ChipTone {
  if (status === "used") return "good";
  if (status === "pending") return "warn";
  if (status === "partial") return "info";
  if (status.startsWith("expired")) return "bad";
  return "neutral";
}

export const statusLabel = (status: BenefitStatus): string => STATUS_LABEL[status];

function Row({ b, large }: { b: BenefitOut; large?: boolean }) {
  const c = b.current;
  if (!c) return null;
  const used = pct(c.used, c.cap);
  const pending = pct(c.pending, c.cap);
  return (
    <li className={`flex items-center gap-3 ${large ? "py-1.5" : "py-1"}`}>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className={`truncate ${large ? "text-base" : "text-sm"} text-ink-200`}>{b.name}</span>
          <span className={`${large ? "text-sm" : "text-[11px]"} whitespace-nowrap text-ink-400`}>
            {c.status === "used" ? (
              "used"
            ) : (
              <>
                <Money value={c.remaining} className="text-ink-200" /> left, {c.days_left} days
              </>
            )}
          </span>
        </div>
        <SplitBar used={used} pending={pending} height="h-1.5" className="mt-1" />
      </div>
      {c.expiring_soon && <Chip tone="warn">soon</Chip>}
    </li>
  );
}

function CardBlock({ card, large }: { card: BenefitCard; large?: boolean }) {
  const [showUsed, setShowUsed] = useState(false);
  const { active, used } = useMemo(() => {
    const sorted = sortBenefits(card.benefits.filter((b) => b.current));
    return { active: sorted.filter((b) => b.current?.status !== "used"), used: sorted.filter((b) => b.current?.status === "used") };
  }, [card.benefits]);
  return (
    <div>
      <div className={`${large ? "text-base" : "text-sm"} font-semibold text-ink-200`}>{card.label}</div>
      <FeeOffset captured={card.captured_ytd} fee={card.annual_fee} offset={card.fee_offset} />
      <ul className="mt-2 divide-y divide-ink-800">
        {active.map((b) => (
          <Row key={b.id} b={b} large={large} />
        ))}
      </ul>
      {used.length > 0 && (
        <button type="button" onClick={() => setShowUsed(!showUsed)} className="mt-1 inline-flex items-center gap-1 text-[11px] text-ink-400 hover:text-ink-200" aria-expanded={showUsed}>
          <ChevronDown size={12} className={showUsed ? "rotate-180" : ""} /> {used.length} fully used this period
        </button>
      )}
      {showUsed && (
        <ul className="divide-y divide-ink-800 opacity-70">
          {used.map((b) => (
            <Row key={b.id} b={b} large={large} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function BenefitsCompactBody({ data, large }: { data: BenefitsData; large?: boolean }) {
  return (
    <div className="space-y-4">
      {data.cards.map((card) => (
        <CardBlock key={card.card} card={card} large={large} />
      ))}
    </div>
  );
}

export function BenefitsWidget({ kiosk }: { kiosk?: boolean }) {
  const q = useBenefits();
  return (
    <Card
      title="Amex benefits"
      envelope={q.data}
      error={q.error}
      onRetry={() => q.refetch()}
      kiosk={kiosk}
      actions={
        !kiosk && (
          <Link to="/benefits" className="text-[11px] text-accent hover:underline">
            View all
          </Link>
        )
      }
    >
      {(d) => <BenefitsCompactBody data={d} large={kiosk} />}
    </Card>
  );
}
