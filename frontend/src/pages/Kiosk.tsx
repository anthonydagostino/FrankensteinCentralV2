import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { KioskContext } from "../lib/kioskContext";

const IDLE_MS = 5000;

/**
 * Wraps the kiosk page: after five idle seconds the cursor is hidden (the .kiosk-idle rule) until the mouse,
 * keyboard or touch wakes it, and the page can be blacked out with the moon button (a click or key wakes it; a
 * nudged mouse does not). Black pixels, not DPMS: the night timer in deploy/kiosk is what turns the panel off.
 */
export function KioskFrame({ children }: { children: ReactNode }) {
  const [idle, setIdle] = useState(false);
  const [dark, setDark] = useState(false);
  const screenOff = useCallback(() => setDark(true), []);
  // the periodic reload that picks up new builds lives in KioskGate (App.tsx) so it also runs while locked
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
  useEffect(() => {
    if (!dark) return;
    const wake = () => setDark(false);
    window.addEventListener("keydown", wake);
    return () => window.removeEventListener("keydown", wake);
  }, [dark]);
  return (
    <KioskContext.Provider value={{ screenOff }}>
      <div className={idle ? "kiosk-idle" : ""}>{children}</div>
      {dark && (
        <button
          type="button"
          onClick={() => setDark(false)}
          className="screen-off fixed inset-0 z-50 h-screen w-screen bg-black"
          aria-label="Screen off, click to wake"
          title="Click to wake"
        />
      )}
    </KioskContext.Provider>
  );
}
