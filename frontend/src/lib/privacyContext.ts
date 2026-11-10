import { createContext, useContext } from "react";

export interface PrivacyContextValue {
  blurred: boolean;
  toggle: () => void;
  setBlurred: (value: boolean) => void;
}

export const PrivacyContext = createContext<PrivacyContextValue>({ blurred: false, toggle: () => {}, setBlurred: () => {} });

export function usePrivacy(): PrivacyContextValue {
  return useContext(PrivacyContext);
}
