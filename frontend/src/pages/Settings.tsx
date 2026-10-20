import { usePublicConfig, useSaveSettings, useSettings, useStatus } from "../api/hooks";
import { Chip } from "../components/Bars";
import { StatusDot } from "../components/Card";
import { formatDateOnly, relativeTime } from "../lib/format";
import { usePrivacy } from "../lib/privacy";

export function SettingsPage() {
  const settings = useSettings();
  const status = useStatus();
  const config = usePublicConfig();
  const save = useSaveSettings();
  const { blurred, setBlurred } = usePrivacy();
  const s = settings.data;
  const cfg = config.data;
  return (
    <main className="mx-auto max-w-[1100px] space-y-4 px-4 py-4">
      <h1 className="text-xl font-semibold text-ink-200">Settings</h1>

      <section className="rounded-xl border border-ink-700 bg-ink-900/80 p-4">
        <h2 className="text-base font-semibold text-ink-200">Amex card accounts</h2>
        <p className="mb-3 text-xs text-ink-400">Each card resolves to a Firefly III account by name. Pin a different account if the match is wrong.</p>
        {!s ? (
          <p className="text-sm text-ink-500">Loading</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {cfg?.cards.map((card) => {
              const resolved = s.card_accounts[card.id];
              return (
                <div key={card.id} className="rounded-lg bg-ink-800/50 p-3">
                  <div className="text-sm font-semibold text-ink-200">{card.label}</div>
                  <div className="text-xs text-ink-400">
                    Resolved: {resolved ? `${resolved.name} (id ${resolved.id}${resolved.pinned ? ", pinned" : ", matched by name"})` : "no account matched"}
                  </div>
                  <select
                    className="mt-2 w-full rounded border border-ink-700 bg-ink-900 px-2 py-1.5 text-sm text-ink-200"
                    value={s.values[`card_account:${card.id}`] ?? ""}
                    onChange={(e) => save.mutate({ [`card_account:${card.id}`]: e.target.value || null })}
                  >
                    <option value="">Automatic (match by name)</option>
                    {s.accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} ({a.type}{a.role ? `, ${a.role}` : ""})
                      </option>
                    ))}
                  </select>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-ink-700 bg-ink-900/80 p-4">
        <h2 className="text-base font-semibold text-ink-200">Preferences</h2>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <label className="block text-xs text-ink-400">
            Default weather location
            <select className="mt-1 w-full rounded border border-ink-700 bg-ink-900 px-2 py-1.5 text-sm text-ink-200" value={cfg?.selected_location ?? ""} onChange={(e) => save.mutate({ weather_location: e.target.value })}>
              {cfg?.locations.map((l) => (
                <option key={l.name} value={l.name}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <div className="text-xs text-ink-400">
            Privacy
            <label className="mt-1 flex items-center gap-2 text-sm text-ink-200">
              <input type="checkbox" checked={blurred} onChange={(e) => setBlurred(e.target.checked)} className="accent-[#4ade80]" /> Blur dollar amounts on the dashboard
            </label>
            <p className="mt-1">Kiosk amounts are {cfg?.privacy.kiosk_hide_amounts ? "blurred" : "visible"} (config/dashboard.yaml, finance.kiosk_hide_amounts).</p>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-ink-700 bg-ink-900/80 p-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-base font-semibold text-ink-200">Integrations</h2>
          {status.data && <Chip tone={status.data.mock_mode ? "warn" : "good"}>{status.data.mock_mode ? "MOCK_MODE on" : "live mode"}</Chip>}
        </div>
        <table className="mt-3 w-full text-xs">
          <thead className="text-left text-ink-400">
            <tr>
              <th className="py-1 font-medium">Module</th>
              <th className="py-1 font-medium">Status</th>
              <th className="py-1 font-medium">Source</th>
              <th className="py-1 font-medium">Last fetch</th>
              <th className="py-1 font-medium">Interval</th>
              <th className="py-1 font-medium">Last error / setup</th>
            </tr>
          </thead>
          <tbody>
            {status.data?.integrations.map((r) => (
              <tr key={r.module} className="border-t border-ink-800">
                <td className="py-1.5 text-ink-200">{r.module}</td>
                <td className="py-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    <StatusDot status={r.status} stale={r.stale} /> {r.status}
                    {r.stale ? " (stale)" : ""}
                  </span>
                </td>
                <td className="py-1.5">{r.mocked ? <Chip tone="warn">mock</Chip> : r.configured ? <Chip tone="good">live</Chip> : <Chip>not configured</Chip>}</td>
                <td className="py-1.5 text-ink-400">{relativeTime(r.fetched_at)}</td>
                <td className="py-1.5 text-ink-400">{r.interval >= 60 ? `${Math.round(r.interval / 60)} min` : `${r.interval} s`}</td>
                <td className="max-w-[320px] truncate py-1.5 text-ink-400" title={r.error ?? ""}>{r.error ?? (!r.configured && !r.mocked ? `set ${r.setup_hint.join(", ")}` : "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-xl border border-ink-700 bg-ink-900/80 p-4 text-sm text-ink-300">
        <h2 className="text-base font-semibold text-ink-200">Benefits catalog</h2>
        <p className="mt-1 text-xs text-ink-400">
          config/benefits.yaml was last verified on <span className="text-ink-200">{s ? formatDateOnly(s.catalog_last_verified, "MMMM d, yyyy") : ""}</span>. Check it against the Benefits page in the Amex app once a quarter and update last_verified.
        </p>
      </section>
    </main>
  );
}
