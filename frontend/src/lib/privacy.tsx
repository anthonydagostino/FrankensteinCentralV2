import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

interface PrivacyContextValue {
  blurred: boolean;
  toggle: () => void;
  setBlurred: (value: boolean) => void;
}

const PrivacyContext = createContext<PrivacyContextValue>({ blurred: false, toggle: () => {}, setBlurred: () => {} });

const STORAGE_KEY = "fc.privacyBlur";

export function readStoredPrivacy(): boolean | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    return raw === "true";
  } catch {
    return null;
  }
}

export function PrivacyProvider({ children, initial, persist }: { children: ReactNode; initial: boolean; persist?: (value: boolean) => void }) {
  const [blurred, setBlurredState] = useState<boolean>(() => readStoredPrivacy() ?? initial);
  useEffect(() => {
    if (readStoredPrivacy() === null) setBlurredState(initial);
  }, [initial]);
  const setBlurred = useCallback(
    (value: boolean) => {
      setBlurredState(value);
      try {
        localStorage.setItem(STORAGE_KEY, String(value));
      } catch {
        /* ignore */
      }
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
