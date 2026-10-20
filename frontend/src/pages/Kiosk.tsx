import { useEffect, useState } from "react";
import type { PublicConfig } from "../api/types";
import { Clock } from "../components/Clock";
import { AttentionStrip } from "../widgets/Attention";
import { BenefitsWidget } from "../widgets/Benefits";
import { CalendarWidget } from "../widgets/Calendar";
import { ContainersWidget } from "../widgets/Containers";
import { PlexWidget } from "../widgets/Plex";
import { WeatherWidget } from "../widgets/Weather";

const RELOAD_MS = 6 * 60 * 60 * 1000;
const IDLE_MS = 5000;

export function Kiosk({ config }: { config?: PublicConfig }) {
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => window.location.reload(), RELOAD_MS);
    return () => clearTimeout(t);
  }, []);
  useEffect(() => {
    let timer = window.setTimeout(() => setIdle(true), IDLE_MS);
    const wake = () => {
      setIdle(false);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setIdle(true), IDLE_MS);
    };
    window.addEventListener("mousemove", wake);
    window.addEventListener("keydown", wake);
    window.addEventListener("touchstart", wake);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("mousemove", wake);
      window.removeEventListener("keydown", wake);
      window.removeEventListener("touchstart", wake);
    };
  }, []);
  return (
    <main className={`min-h-screen bg-ink-950 p-6 text-lg ${idle ? "kiosk-idle" : ""}`}>
      <div className="mb-5 flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <div className="mb-3 text-3xl font-semibold text-ink-200">FrankensteinCentral</div>
          <AttentionStrip location={config?.selected_location} large />
        </div>
        <Clock large />
      </div>
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-7">
          <CalendarWidget kiosk onlyToday />
        </div>
        <div className="col-span-5">
          <WeatherWidget kiosk location={config?.selected_location} />
        </div>
        <div className="col-span-5">
          <BenefitsWidget kiosk />
        </div>
        <div className="col-span-4">
          <PlexWidget kiosk onlyNowPlaying />
        </div>
        <div className="col-span-3">
          <ContainersWidget readOnly kiosk summaryOnly />
        </div>
      </div>
    </main>
  );
}
