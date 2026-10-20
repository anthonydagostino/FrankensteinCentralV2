import { ArrowDownRight, ArrowUpRight, ExternalLink, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFinance, useFinanceSync, useTransactions } from "../api/hooks";
import type { AccountRow, FinanceSummary, TransactionRow } from "../api/types";
import { Chip, ProgressBar } from "../components/Bars";
import { Card } from "../components/Card";
import { Money } from "../components/Money";
import { formatDateOnly, formatMoney, toNumber } from "../lib/format";
import { usePrivacy } from "../lib/privacy";

const PALETTE = ["#4ade80", "#60a5fa", "#f59e0b", "#f472b6", "#a78bfa", "#2dd4bf"];

function Tile({ label, value, sub, href }: { label: string; value: React.ReactNode; sub?: React.ReactNode; href?: string }) {
  return (
    <div className="rounded-lg bg-ink-800/60 p-3">
      <div className="text-[11px] uppercase tracking-wide text-ink-400">{label}</div>
      <div className="mt-1 text-xl font-semibold text-ink-200">{href ? <a href={href} target="_blank" rel="noreferrer" className="hover:underline">{value}</a> : value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-400">{sub}</div>}
    </div>
  );
}

function AccountList({ title, rows, owed }: { title: string; rows: AccountRow[]; owed?: boolean }) {
  if (rows.length === 0) return null;
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">{title}</div>
      <ul className="space-y-0.5">
        {rows.map((a) => (
          <li key={a.id} className="flex items-center justify-between gap-2 rounded px-2 py-1 text-sm hover:bg-ink-800">
            <span className="truncate text-ink-200">{a.name}</span>
            <Money value={owed ? a.owed : a.balance} href={a.url} className={owed ? "text-amber-200" : "text-ink-200"} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function Transactions({ rows }: { rows: TransactionRow[] }) {
  const { blurred } = usePrivacy();
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left text-[11px] uppercase tracking-wide text-ink-400">
          <th className="pb-1 font-medium">Date</th>
          <th className="pb-1 font-medium">Description</th>
          <th className="hidden pb-1 font-medium sm:table-cell">Account</th>
          <th className="hidden pb-1 font-medium md:table-cell">Category</th>
          <th className="pb-1 text-right font-medium">Amount</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t) => (
          <tr key={t.journal_id} className="border-t border-ink-800 hover:bg-ink-800/60">
            <td className="whitespace-nowrap py-1 pr-2 text-ink-400">{formatDateOnly(t.date, "MMM d")}</td>
            <td className="max-w-[220px] truncate py-1 pr-2 text-ink-200" title={t.description}>
              {t.url ? (
                <a href={t.url} target="_blank" rel="noreferrer" className="hover:underline">
                  {t.description}
                </a>
              ) : (
                t.description
              )}
            </td>
            <td className="hidden max-w-[160px] truncate py-1 pr-2 text-ink-400 sm:table-cell">{t.account}</td>
            <td className="hidden py-1 pr-2 text-ink-400 md:table-cell">{t.category ?? ""}</td>
            <td className={`tabular whitespace-nowrap py-1 text-right ${t.sign > 0 ? "text-accent" : t.sign < 0 ? "text-ink-200" : "text-ink-400"} ${blurred ? "privacy-blur" : ""}`}>
              {t.sign === 0 ? "" : t.sign > 0 ? "+" : "-"}
              {formatMoney(t.amount)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function FinanceBody({ data, syncEnabled }: { data: FinanceSummary; syncEnabled: boolean }) {
  const tx = useTransactions(15);
  const sync = useFinanceSync();
  const { blurred } = usePrivacy();
  const [showAll, setShowAll] = useState(false);
  const pace = data.pace_pct;
  const spark = data.daily_spend.map((d) => ({ date: d.date, amount: toNumber(d.amount) }));
  const cats = data.categories.map((c) => ({ ...c, value: toNumber(c.amount) }));
  const fresh = data.freshness;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={fresh.stale ? "warn" : "good"}>{fresh.hours_since !== null ? `Updated from bank ${fresh.hours_since < 1 ? "under 1 h" : `${Math.round(fresh.hours_since)} h`} ago` : "No bank data yet"}</Chip>
        {data.firefly_version && <Chip>Firefly {data.firefly_version}</Chip>}
        {syncEnabled && (
          <button type="button" onClick={() => sync.mutate()} disabled={sync.isPending} className="inline-flex items-center gap-1 rounded border border-ink-600 px-2 py-0.5 text-[11px] text-ink-300 hover:border-accent/50 disabled:opacity-50">
            <RefreshCw size={11} className={sync.isPending ? "animate-spin" : ""} /> Sync now
          </button>
        )}
        {sync.isSuccess && <span className="text-[11px] text-ink-400">Import triggered, refreshing in 90 s</span>}
        {sync.isError && <span className="text-[11px] text-red-300">{(sync.error as Error).message}</span>}
        {data.links.home && (
          <a href={data.links.home} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-[11px] text-ink-400 hover:text-ink-200">
            Open Firefly <ExternalLink size={11} />
          </a>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Net worth" value={<Money value={data.net_worth} whole />} href={data.links.accounts} />
        <Tile
          label="Spent this month"
          value={<Money value={data.mtd_spend} whole />}
          href={data.links.transactions}
          sub={
            pace === null ? (
              "No comparison yet"
            ) : (
              <span className={`inline-flex items-center gap-0.5 ${data.pace === "ahead" ? "text-amber-300" : "text-accent"}`}>
                {data.pace === "ahead" ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                {Math.abs(pace)}% {data.pace === "ahead" ? "ahead of" : "behind"} last month
              </span>
            )
          }
        />
        <Tile label="Left to spend" value={<Money value={data.left_to_spend ?? "0"} whole />} href={data.links.budgets} sub="Across budgets" />
        <Tile label="Bills unpaid" value={<Money value={data.bills_unpaid ?? "0"} whole />} href={data.links.bills} sub={`${data.bills.length} due in 14 days`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg bg-ink-800/40 p-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Daily spend, last 30 days</div>
          <div className={`h-24 ${blurred ? "privacy-blur" : ""}`}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={spark} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="spend" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#4ade80" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#4ade80" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" hide />
                <YAxis hide />
                <Tooltip contentStyle={{ background: "#171e1a", border: "1px solid #2f3a33", fontSize: 12 }} labelFormatter={(l) => formatDateOnly(String(l), "MMM d")} formatter={(v: number) => [formatMoney(v), "Spent"]} />
                <Area type="monotone" dataKey="amount" stroke="#4ade80" fill="url(#spend)" strokeWidth={1.5} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-lg bg-ink-800/40 p-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Top categories this month</div>
          <div className={`h-24 ${blurred ? "privacy-blur" : ""}`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cats} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={90} tick={{ fill: "#97a69c", fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#171e1a", border: "1px solid #2f3a33", fontSize: 12 }} formatter={(v: number) => [formatMoney(v), "Spent"]} cursor={{ fill: "#222b26" }} />
                <Bar dataKey="value" radius={[0, 3, 3, 0]} barSize={10} isAnimationActive={false}>
                  {cats.map((_, i) => (
                    <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="min-w-0 space-y-3">
          <AccountList title="Assets" rows={data.accounts.assets} />
          <AccountList title="Credit cards" rows={data.accounts.credit_cards} owed />
          <AccountList title="Liabilities" rows={data.accounts.liabilities} owed />
        </div>
        <div className="min-w-0">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Budgets this month</div>
          <ul className="space-y-2">
            {data.budgets.length === 0 && <li className="text-xs text-ink-500">No budgets set in Firefly</li>}
            {data.budgets.map((b) => (
              <li key={b.id}>
                <div className="flex justify-between text-xs">
                  <span className="text-ink-200">{b.name}</span>
                  <span className="text-ink-400">
                    <Money value={b.spent} /> / <Money value={b.limit} />
                  </span>
                </div>
                <ProgressBar value={b.pct ?? 0} color={b.level === "over" ? "bg-red-500" : b.level === "warn" ? "bg-amber-400" : "bg-accent"} className="mt-1" label={b.name} />
              </li>
            ))}
          </ul>
        </div>
        <div className="min-w-0">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Upcoming bills</div>
          <ul className="space-y-1">
            {data.bills.length === 0 && <li className="text-xs text-ink-500">Nothing due in the next 14 days</li>}
            {data.bills.map((b) => (
              <li key={b.id} className="flex items-center justify-between rounded px-2 py-1 text-sm hover:bg-ink-800">
                <span className="truncate text-ink-200">
                  {b.name}
                  <span className="ml-2 text-[11px] text-ink-400">{b.days === 0 ? "today" : b.days === 1 ? "tomorrow" : `in ${b.days} days`}</span>
                </span>
                <Money value={b.amount} href={data.links.bills} />
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="min-w-0 overflow-x-auto">
        <div className="mb-1 flex items-center justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Recent transactions</span>
          <button type="button" className="text-[11px] text-ink-400 hover:text-ink-200" onClick={() => setShowAll(!showAll)}>
            {showAll ? "Show fewer" : "Show all 15"}
          </button>
        </div>
        {tx.data?.data ? <Transactions rows={tx.data.data.transactions.slice(0, showAll ? 15 : 6)} /> : <p className="text-xs text-ink-500">Loading transactions</p>}
      </div>
    </div>
  );
}

export function FinanceWidget({ syncEnabled }: { syncEnabled: boolean }) {
  const q = useFinance();
  return (
    <Card title="Finances" envelope={q.data} error={q.error} onRetry={() => q.refetch()}>
      {(d) => <FinanceBody data={d} syncEnabled={syncEnabled} />}
    </Card>
  );
}
