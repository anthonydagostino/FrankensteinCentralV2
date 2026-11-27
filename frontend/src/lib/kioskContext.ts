import { createContext, useContext } from "react";

/** Present only under the kiosk route: lets the glance view offer the screen-off control. */
export const KioskContext = createContext<{ screenOff: () => void } | null>(null);
export const useKiosk = () => useContext(KioskContext);
