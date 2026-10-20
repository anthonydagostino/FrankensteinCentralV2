import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCallback, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { getJson, sendJson } from "./api/client";
import { useMe, usePublicConfig } from "./api/hooks";
import type { PublicConfig } from "./api/types";
import { Header } from "./components/Header";
import { PrivacyProvider } from "./lib/privacy";
import { BenefitsPage } from "./pages/Benefits";
import { Dashboard } from "./pages/Dashboard";
import { Kiosk } from "./pages/Kiosk";
import { LoginPage } from "./pages/Login";
import { SettingsPage } from "./pages/Settings";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => !(error instanceof Error && "status" in error && (error as { status: number }).status === 401) && count < 2,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

function KioskGate() {
  const me = useMe();
  const config = usePublicConfig(!!me.data?.authenticated);
  if (me.isLoading) return <div className="p-8 text-ink-400">Starting kiosk</div>;
  if (!me.data?.authenticated) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8 text-center text-ink-300">
        <div>
          <h1 className="text-2xl font-semibold text-ink-200">Kiosk is locked</h1>
          <p className="mt-2 text-sm">Open /kiosk?token=YOUR_KIOSK_TOKEN once on this device, or sign in on the dashboard first.</p>
        </div>
      </main>
    );
  }
  const hide = config.data?.privacy.kiosk_hide_amounts ?? true;
  return (
    <PrivacyProvider initial={hide} key={`kiosk-${hide}`}>
      <Kiosk config={config.data} />
    </PrivacyProvider>
  );
}

function Shell() {
  const me = useMe();
  const location = useLocation();
  const config = usePublicConfig(!!me.data?.authenticated);
  const persist = useCallback((value: boolean) => {
    sendJson("/api/settings", "POST", { values: { privacy_blur: String(value) } }).catch(() => {});
  }, []);
  useEffect(() => {
    if (me.data?.authenticated) getJson("/api/health").catch(() => {});
  }, [me.data?.authenticated]);
  if (me.isLoading) return <div className="p-8 text-ink-400">Loading</div>;
  if (!me.data?.authenticated) {
    return <LoginPage passwordConfigured={undefined} />;
  }
  const readOnly = me.data.read_only;
  const cfg: PublicConfig | undefined = config.data;
  return (
    <PrivacyProvider initial={cfg?.privacy.hide_amounts_by_default ?? false} persist={readOnly ? undefined : persist}>
      <Header config={cfg} readOnly={readOnly} />
      <Routes location={location}>
        <Route path="/" element={<Dashboard config={cfg} readOnly={readOnly} />} />
        <Route path="/benefits" element={<BenefitsPage readOnly={readOnly} />} />
        <Route path="/settings" element={readOnly ? <Navigate to="/" replace /> : <SettingsPage />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </PrivacyProvider>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/kiosk" element={<KioskGate />} />
          <Route path="/*" element={<Shell />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
