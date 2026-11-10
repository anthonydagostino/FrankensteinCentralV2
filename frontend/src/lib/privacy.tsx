import { useCallback, useMemo, useState, type ReactNode } from "react";
import { PrivacyContext } from "./privacyContext";

/**
 * Privacy blur for dollar amounts. The server setting (`initial`, from /api/config/public) is the source
 * of truth so every device agrees; toggling calls `persist` when given (dashboard) or stays local (kiosk).
 */
export function PrivacyProvider({ children, initial, persist }: { children: ReactNode; initial: boolean; persist?: (value: boolean) => void }) {
  const [blurred, setBlurredState] = useState<boolean>(initial);
  // A changed server value wins over the local toggle: state is adjusted during render, not in an effect.
  const [seenInitial, setSeenInitial] = useState(initial);
  if (initial !== seenInitial) {
    setSeenInitial(initial);
    setBlurredState(initial);
  }
  const setBlurred = useCallback(
    (value: boolean) => {
      setBlurredState(value);
      persist?.(value);
    },
    [persist],
  );
  const toggle = useCallback(() => setBlurred(!blurred), [blurred, setBlurred]);
  const value = useMemo(() => ({ blurred, toggle, setBlurred }), [blurred, toggle, setBlurred]);
  return <PrivacyContext.Provider value={value}>{children}</PrivacyContext.Provider>;
}
