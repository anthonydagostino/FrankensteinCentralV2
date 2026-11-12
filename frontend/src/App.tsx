import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCallback, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiError, sendJson } from "./api/client";
import { useMe, usePublicConfig } from "./api/hooks";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Header } from "./components/Header";
import { PrivacyProvider } from "./lib/privacy";
import { BenefitsPage } from "./pages/Benefits";
import { Dashboard } from "./pages/Dashboard";
import { FitnessPage } from "./pages/Fitness";
import { Kiosk } from "./pages/Kiosk";
import { LoginPage } from "./pages/Login";
import { SettingsPage } from "./pages/Settings";

const isUnauthorized = (error: unknown) => error instanceof ApiError && error.status === 401;

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    // A 401 on any query means the session cookie expired: re-check auth so the login page comes back.
    onError: (error) => {
      if (isUnauthorized(error)) void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  }),
  defaultOptions: {
    queries: {
      retry: (count, error) => !isUnauthorized(error) && count < 2,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

const KIOSK_RELOAD_MS = 6 * 60 * 60 * 1000;

/** The kiosk route: locked until the kiosk cookie is present, then the full-screen page. */
function KioskGate() {
  // Keep polling auth while locked so a backend restart at boot cannot strand the kiosk on the locked screen.
  const me = useMe({ refetchInterval: 30_000 });
  const config = usePublicConfig(!!me.data?.authenticated);
  // The reload (to pick up new builds) lives here so it also runs while the kiosk is locked.
  useEffect(() => {
    const t = setTimeout(() => window.location.reload(), KIOSK_RELOAD_MS);
    return () => clearTimeout(t);
  }, []);
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
  return (
    <PrivacyProvider initial={config.data?.privacy.kiosk_hide_amounts ?? true}>
      <Kiosk config={config.data} />
    </PrivacyProvider>
  );
}

/** Everything behind the login: header, dashboard, benefits, and settings. */
function Shell() {
  const me = useMe();
  const config = usePublicConfig(!!me.data?.authenticated);
  const persist = useCallback((value: boolean) => {
    sendJson("/api/settings", "POST", { values: { privacy_blur: String(value) } }).catch(() => {});
  }, []);
  if (me.isLoading) return <div className="p-8 text-ink-400">Loading</div>;
  if (!me.data?.authenticated) return <LoginPage passwordConfigured={me.data?.password_configured} />;
  const readOnly = me.data.read_only;
  const cfg = config.data;
  return (
    <PrivacyProvider initial={cfg?.privacy.hide_amounts_by_default ?? false} persist={readOnly ? undefined : persist}>
      <Header config={cfg} readOnly={readOnly} />
      <Routes>
        <Route path="/" element={<Dashboard config={cfg} readOnly={readOnly} />} />
        <Route path="/benefits" element={<BenefitsPage readOnly={readOnly} />} />
        <Route path="/fitness" element={<Navigate to="/fitness/weight" replace />} />
        <Route path="/fitness/:view" element={<FitnessPage readOnly={readOnly} />} />
        <Route path="/settings" element={readOnly ? <Navigate to="/" replace /> : <SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </PrivacyProvider>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary name="FrankensteinCentral">
          <Routes>
            <Route path="/kiosk" element={<KioskGate />} />
            <Route path="/*" element={<Shell />} />
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
