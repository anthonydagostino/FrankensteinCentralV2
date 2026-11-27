import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { usePrivacy } from "../lib/privacyContext";

/**
 * The eye that blurs or reveals every amount.
 * Fitts: a 40px target. Pulse to confirm: one beat on press. Crossfade icons with blur: the swapped icon fades in
 * from a soft blur (keyed on state so it re-mounts). Doherty: the state flips on the click itself, nothing waits.
 */
export function PrivacyToggle({ size = 20, className = "" }: { size?: number; className?: string }) {
  const { blurred, toggle } = usePrivacy();
  const [pulse, setPulse] = useState(0);
  return (
    <button
      type="button"
      onClick={() => {
        toggle();
        setPulse((n) => n + 1);
      }}
      className={`inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-300 hover:bg-ink-700 hover:text-ink-200 ${className}`}
      title={blurred ? "Show amounts" : "Hide amounts"}
      aria-label={blurred ? "Show amounts" : "Hide amounts"}
      aria-pressed={blurred}
    >
      <span key={`${blurred}-${pulse}`} className={`inline-flex ${pulse ? "confirm-pulse icon-in" : ""}`}>
        {blurred ? <EyeOff size={size} /> : <Eye size={size} />}
      </span>
    </button>
  );
}
