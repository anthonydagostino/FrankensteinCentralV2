import { Activity, LayoutGrid, LogOut, Settings as SettingsIcon, BadgeDollarSign, MonitorPlay } from "lucide-react";
import { PrivacyToggle } from "./PrivacyToggle";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useLogout } from "../api/hooks";
import type { PublicConfig } from "../api/types";
import { greeting } from "../lib/format";
import { useNow } from "../lib/useNow";
import { writeViewMode } from "../lib/glance";
import { Clock } from "./Clock";
import { DynamicIcon } from "../lib/icons";

export function Header({ config, readOnly }: { config?: PublicConfig; readOnly: boolean }) {
  const logout = useLogout();
  const now = useNow(60_000);
  const navigate = useNavigate();
  const nav = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-2 py-1 text-sm text-ink-300 hover:bg-ink-700 hover:text-ink-200 ${isActive ? "bg-ink-800 text-ink-200" : ""}`;
  return (
    <header className="sticky top-0 z-30 border-b border-ink-700/80 bg-ink-950/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2">
        <Link to="/" className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent/15 font-black text-accent">F</span>
          <div className="leading-tight">
            <div className="text-base font-semibold text-ink-200">FrankensteinCentral</div>
            <div className="hidden text-[11px] text-ink-400 sm:block">
              {config ? greeting(now, config.owner_name) : ""}
              {config?.features.mock_mode ? " (mock data)" : ""}
            </div>
          </div>
        </Link>
        <nav className="order-last flex w-full items-center gap-1 sm:order-none sm:ml-4 sm:w-auto">
          <NavLink to="/" end className={nav} onClick={() => writeViewMode("full")}>
            Dashboard
          </NavLink>
          <NavLink to="/benefits" className={nav}>
            <span className="inline-flex items-center gap-1">
              <BadgeDollarSign size={14} /> Benefits
            </span>
          </NavLink>
          <NavLink to="/fitness" className={nav}>
            <span className="inline-flex items-center gap-1">
              <Activity size={14} /> Fitness
            </span>
          </NavLink>
          {!readOnly && (
            <NavLink to="/settings" className={nav}>
              <span className="inline-flex items-center gap-1">
                <SettingsIcon size={14} /> Settings
              </span>
            </NavLink>
          )}
          {config?.features.kiosk && (
            <NavLink to="/kiosk" className={nav} title="Kiosk view" aria-label="Kiosk view">
              <MonitorPlay size={14} />
            </NavLink>
          )}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <div className="hidden items-center gap-1 md:flex">
            {config?.links.map((l) => (
              <a
                key={l.name}
                href={l.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-md border border-ink-700 px-2 py-1 text-xs text-ink-300 hover:border-accent/50 hover:text-ink-200"
                title={l.name}
              >
                <DynamicIcon name={l.icon} size={13} /> {l.name}
              </a>
            ))}
          </div>
          <Clock />
          <button
            type="button"
            onClick={() => {
              writeViewMode("glance");
              navigate("/glance");
            }}
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-300 hover:bg-ink-700 hover:text-ink-200"
            title="Glance view: one screen, no scrolling"
            aria-label="Glance view"
          >
            <LayoutGrid size={18} />
          </button>
          <PrivacyToggle size={18} />
          {!readOnly && (
            <button
              type="button"
              onClick={() => logout.mutate()}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-300 hover:bg-ink-700 hover:text-ink-200"
              title="Log out"
              aria-label="Log out"
            >
              <LogOut size={18} />
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
