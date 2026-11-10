import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

interface PrivacyContextValue {
  blurred: boolean;
  toggle: () => void;
  setBlurred: (value: boolean) => void;
}

const PrivacyContext = createContext<PrivacyContextValue>({ blurred: false, toggle: () => {}, setBlurred: () => {} });

/**
 * Privacy blur for dollar amounts. The server setting (`initial`, from /api/config/public) is the source
 * of truth so every device agrees; toggling calls `persist` when given (dashboard) or stays local (kiosk).
 */
export function PrivacyProvider({ children, initial, persist }: { children: ReactNode; initial: boolean; persist?: (value: boolean) => void }) {
  const [blurred, setBlurredState] = useState<boolean>(initial);
  useEffect(() => setBlurredState(initial), [initial]);
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

export function usePrivacy() {
  return useContext(PrivacyContext);
}
