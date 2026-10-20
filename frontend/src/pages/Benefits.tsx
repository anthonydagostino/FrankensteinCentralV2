import { Check, ClipboardCopy, Info, Trash2 } from "lucide-react";
import { useState } from "react";
import { useBenefits, useDeleteOverride, useManualUsage, useSaveOverride, useUnclassified } from "../api/hooks";
import type { BenefitOut, BenefitsData, PeriodResult, UnclassifiedItem } from "../api/types";
import { Chip, ProgressBar, SplitBar } from "../components/Bars";
import { Card, ErrorState, SetupHint, Skeleton } from "../components/Card";
import { Modal } from "../components/Modal";
import { Money } from "../components/Money";
import { formatDateOnly, pct } from "../lib/format";
import { sortBenefits, statusLabel, statusTone } from "../widgets/Benefits";

function periodLabel(p: PeriodResult): string {
  return p.label;
}

function Tile({ b, onOpen }: { b: BenefitOut; onOpen: (b: BenefitOut) => void }) {
  const c = b.current;
  return (
    <button type="button" onClick={() => onOpen(b)} className="flex min-w-0 flex-col rounded-lg border border-ink-700 bg-ink-800/50 p-3 text-left hover:border-accent/40">
      <div className="flex w-full items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-ink-200">{b.name}</div>
          <div className="text-[11px] text-ink-400">{c ? periodLabel(c) : b.active_until ? `Retired ${formatDateOnly(b.active_until)}` : "Not active"}</div>
        </div>
        {c && <Chip tone={c.expiring_soon ? "warn" : statusTone(c.status)} className="shrink-0">{c.expiring_soon ? `${c.days_left} days left` : statusLabel(c.status)}</Chip>}
      </div>
      {c ? (
        <>
          <SplitBar used={pct(c.used, c.cap)} pending={pct(c.pending, c.cap)} className="mt-3" />
          <div className="mt-1 flex w-full flex-wrap justify-between gap-x-2 text-[11px] text-ink-400">
            <span>
              <Money value={c.used} className="text-accent" /> used
            </span>
            {Number(c.pending) > 0 && (
              <span>
                <Money value={c.pending} className="text-amber-300" /> pending
              </span>
            )}
            <span>
              <Money value={c.remaining} className="text-ink-200" /> of <Money value={c.cap} /> left
            </span>
          </div>
          {b.period === "multi_year" && c.next_eligible && <div className="mt-1 text-[11px] text-ink-400">Next eligible {formatDateOnly(c.next_eligible)}</div>}
          {c.missing_credit && (
            <div className="mt-2 flex items-start gap-1 text-[11px] text-amber-300">
              <Info size={12} className="mt-0.5 shrink-0" /> {c.missing_credit}
            </div>
          )}
        </>
      ) : (
        <div className="mt-3 text-[11px] text-ink-500">History only</div>
      )}
    </button>
  );
}

function EvidenceDrawer({ b, onClose, onWrong }: { b: BenefitOut; onClose: () => void; onWrong: (journalId: number) => void }) {
  const kinds: Record<string, string> = { purchase: "Purchase", statement_credit: "Statement credit", merchant_refund: "Merchant refund", credit_clawback: "Clawback" };
  return (
    <Modal title={b.name} onClose={onClose} wide>
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap gap-2 text-[11px] text-ink-400">
          <Chip>{b.tracking.replace("_", " ")}</Chip>
          <Chip>{b.period.replace("_", " ")}</Chip>
          <Chip>
            cap <Money value={b.cap} />
          </Chip>
          {b.enrollment_required && <Chip tone="info">enrollment required</Chip>}
        </div>
        {b.notes && <p className="text-xs text-ink-400">{b.notes}</p>}
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Periods</div>
          <table className="w-full text-xs">
            <thead className="text-left text-ink-400">
              <tr>
                <th className="py-1 font-medium">Period</th>
                <th className="py-1 text-right font-medium">Cap</th>
                <th className="py-1 text-right font-medium">Used</th>
                <th className="py-1 text-right font-medium">Pending</th>
                <th className="py-1 text-right font-medium">Left</th>
                <th className="py-1 pl-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {[...(b.current ? [b.current] : []), ...b.history].sort((x, y) => (x.start ?? "").localeCompare(y.start ?? "")).reverse().map((p) => (
                <tr key={p.period_key} className={`border-t border-ink-800 ${b.current?.period_key === p.period_key ? "bg-accent/5" : ""}`}>
                  <td className="py-1 text-ink-200">{p.label}</td>
                  <td className="py-1 text-right"><Money value={p.cap} /></td>
                  <td className="py-1 text-right text-accent"><Money value={p.used} /></td>
                  <td className="py-1 text-right text-amber-300"><Money value={p.pending} /></td>
                  <td className="py-1 text-right"><Money value={p.remaining} /></td>
                  <td className="py-1 pl-2"><Chip tone={statusTone(p.status)}>{statusLabel(p.status)}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Evidence ({b.evidence.length})</div>
          {b.evidence.length === 0 && <p className="text-xs text-ink-500">No matching transactions in the window</p>}
          <ul className="divide-y divide-ink-800">
            {[...b.evidence].reverse().map((e) => (
              <li key={e.journal_id} className="flex flex-wrap items-center gap-2 py-1.5 text-xs">
                <span className="w-14 shrink-0 text-ink-400">{formatDateOnly(e.date)}</span>
                <span className="w-24 shrink-0">
                  <Chip tone={e.kind === "statement_credit" ? "good" : e.kind === "purchase" ? "neutral" : e.kind === "merchant_refund" ? "info" : "bad"}>{kinds[e.kind] ?? e.kind}</Chip>
                </span>
                <span className="min-w-0 flex-1 truncate text-ink-200" title={e.description}>
                  {e.description}
                  {e.note && <span className="ml-1 text-ink-400">({e.note})</span>}
                </span>
                <span className="shrink-0 text-ink-400">{e.period_key}</span>
                {e.attribution === "by_credit_date" && <Info size={12} className="shrink-0 text-ink-400" aria-label="Attributed by credit date" />}
                {e.confidence && <Chip tone={e.confidence === "high" ? "good" : e.confidence === "medium" ? "warn" : "bad"}>{e.override ? "override" : e.confidence}</Chip>}
                <span className="w-16 shrink-0 text-right"><Money value={e.amount} /></span>
                {e.kind !== "purchase" && (
                  <button type="button" onClick={() => onWrong(e.journal_id)} className="shrink-0 rounded border border-ink-600 px-1.5 py-0.5 text-[10px] text-ink-300 hover:border-red-400 hover:text-red-200">
                    this is wrong
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Modal>
  );
}

function ReclassifyModal({ item, benefits, onClose }: { item: { journal_id: number; description: string; amount: string; date: string }; benefits: { id: string; name: string; card: string }[]; onClose: () => void }) {
  const save = useSaveOverride();
  const [cls, setCls] = useState("statement_credit");
  const [benefitId, setBenefitId] = useState(benefits[0]?.id ?? "");
  const [period, setPeriod] = useState("");
  const needsBenefit = cls === "statement_credit";
  return (
    <Modal title="Reclassify transaction" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <p className="text-ink-300">
          {formatDateOnly(item.date)} · {item.description} · <Money value={item.amount} />
        </p>
        <label className="block text-xs text-ink-400">
          This is
          <select value={cls} onChange={(e) => setCls(e.target.value)} className="mt-1 w-full rounded border border-ink-700 bg-ink-800 px-2 py-1.5 text-sm text-ink-200">
            <option value="statement_credit">a statement credit for a benefit</option>
            <option value="merchant_refund">a merchant refund</option>
            <option value="payment">a payment</option>
            <option value="ignore">nothing, ignore it</option>
          </select>
        </label>
        {needsBenefit && (
          <label className="block text-xs text-ink-400">
            Benefit
            <select value={benefitId} onChange={(e) => setBenefitId(e.target.value)} className="mt-1 w-full rounded border border-ink-700 bg-ink-800 px-2 py-1.5 text-sm text-ink-200">
              {benefits.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.card === "amex_gold" ? "Gold" : "Platinum"}: {b.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {needsBenefit && (
          <label className="block text-xs text-ink-400">
            Period key (optional, for example 2026-Q4 or 2026-M10)
            <input value={period} onChange={(e) => setPeriod(e.target.value)} className="mt-1 w-full rounded border border-ink-700 bg-ink-800 px-2 py-1.5 text-sm text-ink-200" placeholder="auto" />
          </label>
        )}
        {save.isError && <p className="text-xs text-red-300">{(save.error as Error).message}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-3 py-1.5 text-ink-300 hover:bg-ink-700">
            Cancel
          </button>
          <button
            type="button"
            disabled={save.isPending}
            onClick={() => save.mutate({ journal_id: item.journal_id, classification: cls, benefit_id: needsBenefit ? benefitId : null, period_key: period || null }, { onSuccess: onClose })}
            className="rounded bg-accent/20 px-3 py-1.5 font-medium text-accent hover:bg-accent/30 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Unclassified({ readOnly }: { readOnly: boolean }) {
  const q = useUnclassified();
  const del = useDeleteOverride();
  const [edit, setEdit] = useState<UnclassifiedItem | null>(null);
  const [copied, setCopied] = useState<number | null>(null);
  const data = q.data?.data;
  return (
    <Card title="Unclassified deposits" envelope={q.data} error={q.error} onRetry={() => q.refetch()}>
      {(d) => (
        <div className="space-y-4">
          <p className="text-xs text-ink-400">Deposits on the cards from the last 120 days that the engine could not place, plus low confidence guesses. Label them here; the pattern suggestion can be pasted into config/benefits.yaml (the file is never edited automatically).</p>
          {d.items.length === 0 ? (
            <p className="text-sm text-ink-500">Nothing to review</p>
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-ink-400">
                <tr>
                  <th className="py-1 font-medium">Date</th>
                  <th className="py-1 font-medium">Description</th>
                  <th className="hidden py-1 font-medium sm:table-cell">Account</th>
                  <th className="py-1 text-right font-medium">Amount</th>
                  <th className="py-1 pl-2 font-medium">Engine guess</th>
                  <th className="py-1 pl-2 font-medium">Pattern</th>
                  <th className="py-1"></th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((it) => (
                  <tr key={it.journal_id} className="border-t border-ink-800">
                    <td className="py-1.5 pr-2 text-ink-400">{formatDateOnly(it.date)}</td>
                    <td className="max-w-[200px] truncate py-1.5 pr-2 text-ink-200" title={it.description}>{it.description}</td>
                    <td className="hidden py-1.5 pr-2 text-ink-400 sm:table-cell">{it.account}</td>
                    <td className="py-1.5 text-right"><Money value={it.amount} /></td>
                    <td className="py-1.5 pl-2">{it.kind === "unclassified_deposit" ? <Chip>unclassified</Chip> : <Chip tone="warn">{it.kind.replace("_", " ")} ({it.confidence})</Chip>}</td>
                    <td className="py-1.5 pl-2">
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded border border-ink-700 px-1.5 py-0.5 font-mono text-[10px] text-ink-300 hover:border-accent/50"
                        title={it.suggested_pattern}
                        onClick={() => { navigator.clipboard?.writeText(it.suggested_pattern); setCopied(it.journal_id); setTimeout(() => setCopied(null), 1500); }}
                      >
                        {copied === it.journal_id ? <Check size={10} /> : <ClipboardCopy size={10} />} {it.suggested_pattern.length > 18 ? `${it.suggested_pattern.slice(0, 18)}…` : it.suggested_pattern}
                      </button>
                    </td>
                    <td className="py-1.5 text-right">
                      {!readOnly && (
                        <button type="button" onClick={() => setEdit(it)} className="rounded bg-ink-700 px-2 py-0.5 text-ink-200 hover:bg-ink-600">
                          Label
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
          {d.overrides.length > 0 && (
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Saved overrides</div>
              <ul className="divide-y divide-ink-800 text-xs">
                {d.overrides.map((o) => (
                  <li key={o.id} className="flex items-center gap-2 py-1">
                    <span className="text-ink-400">journal {o.firefly_journal_id}</span>
                    <Chip>{o.classification.replace("_", " ")}</Chip>
                    {o.benefit_id && <span className="text-ink-300">{o.benefit_id}</span>}
                    {o.period_key && <span className="text-ink-400">{o.period_key}</span>}
                    {!readOnly && (
                      <button type="button" onClick={() => del.mutate(o.id)} className="ml-auto rounded p-1 text-ink-400 hover:text-red-300" title="Remove override">
                        <Trash2 size={12} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {edit && data && <ReclassifyModal item={edit} benefits={data.benefits} onClose={() => setEdit(null)} />}
        </div>
      )}
    </Card>
  );
}

function ManualRow({ b, readOnly }: { b: BenefitOut; readOnly: boolean }) {
  const manual = useManualUsage();
  const periods = [...(b.current ? [b.current] : []), ...b.history].filter((p) => !!p.start).sort((x, y) => (y.start ?? "").localeCompare(x.start ?? "")).slice(0, 6);
  return (
    <div className="rounded-lg bg-ink-800/50 p-3">
      <div className="text-sm font-semibold text-ink-200">{b.name}</div>
      <div className="text-[11px] text-ink-400">{b.notes}</div>
      <ul className="mt-2 divide-y divide-ink-800">
        {periods.map((p) => {
          const used = p.manual_entry !== null;
          return (
            <li key={p.period_key} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5 text-xs">
              <span className="w-28 text-ink-300">{p.label}</span>
              <label className="inline-flex items-center gap-1 text-ink-200">
                <input type="checkbox" checked={used} disabled={readOnly} onChange={(e) => manual.mutate({ benefit_id: b.id, period_key: p.period_key, used: e.target.checked })} className="accent-[#4ade80]" /> Used
              </label>
              <span className="text-ink-400">
                of <Money value={p.cap} />
              </span>
              <input
                type="number"
                step="0.01"
                min="0"
                disabled={readOnly}
                defaultValue={p.manual_entry ?? ""}
                placeholder="amount"
                className="w-24 rounded border border-ink-700 bg-ink-900 px-2 py-0.5 text-right text-xs text-ink-200"
                onBlur={(e) => {
                  if (e.target.value !== "" && e.target.value !== (p.manual_entry ?? "")) manual.mutate({ benefit_id: b.id, period_key: p.period_key, used: true, amount: e.target.value });
                }}
              />
              <Chip tone={statusTone(p.status)}>{statusLabel(p.status)}</Chip>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function CardSection({ card, onOpen }: { card: BenefitsData["cards"][number]; onOpen: (b: BenefitOut) => void }) {
  const offset = card.fee_offset ?? 0;
  return (
    <section className="rounded-xl border border-ink-700 bg-ink-900/80 p-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-ink-200">{card.label}</h2>
          <div className="text-xs text-ink-400">{card.account ? `Firefly account: ${card.account.name}` : "No Firefly account matched"}</div>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
          <div>
            <div className="text-ink-400">Captured YTD</div>
            <div className="text-base font-semibold text-accent"><Money value={card.captured_ytd} /></div>
          </div>
          <div>
            <div className="text-ink-400">Annual fee</div>
            <div className="text-base font-semibold text-ink-200"><Money value={card.annual_fee} /></div>
          </div>
          <div>
            <div className="text-ink-400">Still available</div>
            <div className="text-base font-semibold text-ink-200"><Money value={card.still_available} /></div>
          </div>
          <div>
            <div className="text-ink-400">Left on the table</div>
            <div className="text-base font-semibold text-amber-300"><Money value={card.left_on_table_ytd} /></div>
          </div>
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-400">
        <span>Fee offset {Math.round(offset * 100)}%</span>
        <ProgressBar value={offset * 100} color={offset >= 1 ? "bg-accent" : "bg-sky-400"} className="flex-1" label="Fee offset" />
      </div>
      <div className="mt-4 grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {sortBenefits(card.benefits).map((b) => (
          <Tile key={b.id} b={b} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}

export function BenefitsPage({ readOnly }: { readOnly: boolean }) {
  const q = useBenefits();
  const unclassified = useUnclassified();
  const [open, setOpen] = useState<BenefitOut | null>(null);
  const [wrong, setWrong] = useState<number | null>(null);
  const env = q.data;
  const benefitsList = unclassified.data?.data?.benefits ?? [];
  const wrongItem = wrong !== null && open ? open.evidence.find((e) => e.journal_id === wrong) : null;
  return (
    <main className="mx-auto max-w-[1400px] space-y-4 px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold text-ink-200">Amex benefits</h1>
        {env?.data && <span className="text-xs text-ink-400">Catalog verified {formatDateOnly(env.data.catalog_last_verified)} · {env.data.year}</span>}
      </div>
      {q.error && !env && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
      {!env && !q.error && <Skeleton className="h-64 w-full" />}
      {env?.status === "disabled" && <SetupHint title="Benefits" vars={env.setup_hint} message="Benefits are computed from Firefly III transactions. Set these variables in .env and restart:" />}
      {env?.data && env.data.cards.map((card) => <CardSection key={card.card} card={card} onOpen={setOpen} />)}
      {env?.data && env.status !== "disabled" && <Unclassified readOnly={readOnly} />}
      {env?.data && (
        <section className="rounded-xl border border-ink-700 bg-ink-900/80 p-4">
          <h2 className="text-base font-semibold text-ink-200">Manual benefits</h2>
          <p className="mb-3 text-xs text-ink-400">These credits never touch the card statement (Uber Cash lands in the Uber app), so mark them by hand.</p>
          <div className="grid gap-3 md:grid-cols-2">
            {env.data.cards.flatMap((c) => c.benefits.filter((b) => b.tracking === "manual")).map((b) => (
              <ManualRow key={b.id} b={b} readOnly={readOnly} />
            ))}
          </div>
        </section>
      )}
      {open && <EvidenceDrawer b={open} onClose={() => setOpen(null)} onWrong={(id) => setWrong(id)} />}
      {wrongItem && <ReclassifyModal item={wrongItem} benefits={benefitsList} onClose={() => setWrong(null)} />}
    </main>
  );
}
