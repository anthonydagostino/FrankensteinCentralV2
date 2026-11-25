import { useEffect, useState } from "react";
import type { ReactNode } from "react";

const IDLE_MS = 5000;

/** Wraps the kiosk page: after five idle seconds the cursor is hidden (the .kiosk-idle rule) until the mouse, keyboard or touch wakes it. */
export function KioskFrame({ children }: { children: ReactNode }) {
  const [idle, setIdle] = useState(false);
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
  return <div className={idle ? "kiosk-idle" : ""}>{children}</div>;
}
