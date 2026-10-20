import { ExternalLink, KeyRound, Shield, ShieldOff } from "lucide-react";
import { useVault } from "../api/hooks";
import { Card } from "../components/Card";

export function VaultWidget() {
  const q = useVault();
  return (
    <Card title="Vaultwarden" envelope={q.data} error={q.error} onRetry={() => q.refetch()}>
      {(d, env) => {
        const online = d.online && env.status !== "error";
        const backup = d.backup;
        return (
          <div className="flex items-center gap-4">
            <div className={`grid h-14 w-14 place-items-center rounded-xl ${online ? "bg-accent/15 text-accent" : "bg-red-500/15 text-red-300"}`}>{online ? <Shield size={30} /> : <ShieldOff size={30} />}</div>
            <div className="min-w-0 flex-1">
              <div className={`text-sm font-semibold ${online ? "text-ink-200" : "text-red-300"}`}>
                {online ? "Online" : "Down"}
                {d.version ? `, v${d.version}` : ""}
                {d.latency_ms !== null ? `, ${d.latency_ms} ms` : ""}
              </div>
              {!online && d.error && <div className="truncate text-xs text-red-300">{d.error}</div>}
              {backup && backup.available && backup.age_hours !== null && backup.age_hours !== undefined && (
                <div className={`text-xs ${backup.age_hours > 48 ? "text-amber-300" : "text-ink-400"}`}>Last backup {backup.age_hours < 1 ? "under 1 h" : `${Math.round(backup.age_hours)} h`} ago</div>
              )}
              {backup && !backup.available && <div className="text-xs text-amber-300">{backup.error}</div>}
              <div className="mt-2 flex items-center gap-2">
                {d.public_url && (
                  <a href={d.public_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md bg-accent/15 px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent/25">
                    <KeyRound size={14} /> Open Vault <ExternalLink size={12} />
                  </a>
                )}
                {d.admin_url && (
                  <a href={d.admin_url} target="_blank" rel="noreferrer" className="text-xs text-ink-400 hover:text-ink-200">
                    Admin
                  </a>
                )}
              </div>
            </div>
          </div>
        );
      }}
    </Card>
  );
}
