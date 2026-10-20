import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getJson, sendJson } from "./client";
import type {
  AttentionData, BenefitsData, CalendarData, CardData, ContainersData, Envelope, FinanceSummary, Me, PlexData, ProbesData, PublicConfig, RecurringData, SettingsData, StatusRow, TransactionRow, UnclassifiedData, VaultData, WeatherData,
} from "./types";

const MIN = 60_000;

function envelopeQuery<T>(key: unknown[], url: string, interval: number, enabled = true) {
  return useQuery<Envelope<T>>({ queryKey: key, queryFn: () => getJson<Envelope<T>>(url), refetchInterval: interval, enabled, staleTime: Math.min(interval, 30_000) });
}

export const useMe = () => useQuery<Me>({ queryKey: ["me"], queryFn: () => getJson<Me>("/api/auth/me"), staleTime: 30_000, retry: false });
export const usePublicConfig = (enabled = true) => useQuery<PublicConfig>({ queryKey: ["config"], queryFn: () => getJson<PublicConfig>("/api/config/public"), staleTime: 5 * MIN, enabled });

export const useAttention = (location?: string) => envelopeQuery<AttentionData>(["attention", location], `/api/attention${location ? `?location=${encodeURIComponent(location)}` : ""}`, MIN);
export const useWeather = (location?: string) => envelopeQuery<WeatherData>(["weather", location], `/api/weather${location ? `?location=${encodeURIComponent(location)}` : ""}`, 2 * MIN);
export const useCalendar = (days = 7) => envelopeQuery<CalendarData>(["calendar", days], `/api/calendar?days=${days}`, 2 * MIN);
export const useFinance = () => envelopeQuery<FinanceSummary>(["finance"], "/api/finance/summary", 5 * MIN);
export const useTransactions = (limit = 15) => envelopeQuery<{ transactions: TransactionRow[] }>(["transactions", limit], `/api/finance/transactions?limit=${limit}`, 5 * MIN);
export const useRecurring = () => envelopeQuery<RecurringData>(["recurring"], "/api/finance/recurring", 5 * MIN);
export const useCards = () => envelopeQuery<{ cards: CardData[] }>(["cards"], "/api/cards", 5 * MIN);
export const useBenefits = (year?: number) => envelopeQuery<BenefitsData>(["benefits", year], `/api/benefits${year ? `?year=${year}` : ""}`, 5 * MIN);
export const useUnclassified = (enabled = true) => envelopeQuery<UnclassifiedData>(["unclassified"], "/api/benefits/unclassified", 5 * MIN, enabled);
export const usePlex = () => envelopeQuery<PlexData>(["plex"], "/api/plex", 30_000);
export const useVault = () => envelopeQuery<VaultData>(["vault"], "/api/vault", MIN);
export const useContainers = () => envelopeQuery<ContainersData>(["containers"], "/api/containers", 15_000);
export const useProbes = () => envelopeQuery<ProbesData>(["probes"], "/api/probes", MIN);
export const useStatus = () => useQuery<{ integrations: StatusRow[]; mock_mode: boolean }>({ queryKey: ["status"], queryFn: () => getJson("/api/status"), refetchInterval: 30_000 });
export const useSettings = () => useQuery<SettingsData>({ queryKey: ["settings"], queryFn: () => getJson<SettingsData>("/api/settings") });

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, string | null>) => sendJson<{ ok: boolean }>("/api/settings", "POST", { values }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["config"] });
      qc.invalidateQueries({ queryKey: ["cards"] });
      qc.invalidateQueries({ queryKey: ["benefits"] });
      qc.invalidateQueries({ queryKey: ["weather"] });
    },
  });
}

export function useSaveOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { journal_id: number; classification: string; benefit_id?: string | null; period_key?: string | null; note?: string | null }) => sendJson<{ ok: boolean }>("/api/benefits/overrides", "POST", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["benefits"] });
      qc.invalidateQueries({ queryKey: ["unclassified"] });
      qc.invalidateQueries({ queryKey: ["cards"] });
      qc.invalidateQueries({ queryKey: ["attention"] });
    },
  });
}

export function useDeleteOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => sendJson<{ ok: boolean }>(`/api/benefits/overrides/${id}`, "DELETE"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["benefits"] });
      qc.invalidateQueries({ queryKey: ["unclassified"] });
    },
  });
}

export function useManualUsage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { benefit_id: string; period_key: string; amount?: string | null; used: boolean; note?: string | null }) => sendJson<{ ok: boolean }>("/api/benefits/manual", "POST", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["benefits"] });
      qc.invalidateQueries({ queryKey: ["attention"] });
    },
  });
}

export function useRestartContainer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sendJson<{ ok: boolean }>(`/api/containers/${id}/restart`, "POST"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["containers"] }),
  });
}

export function useRecurringIgnore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { key: string; ignore: boolean }) => sendJson<{ ok: boolean }>("/api/finance/recurring/ignore", "POST", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recurring"] });
      qc.invalidateQueries({ queryKey: ["attention"] });
    },
  });
}

export function useFinanceSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => sendJson<{ ok: boolean; refresh_in_seconds?: number }>("/api/finance/sync", "POST"),
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["finance"] }), 95_000),
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (password: string) => sendJson<{ ok: boolean }>("/api/auth/login", "POST", { password }),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => sendJson<{ ok: boolean }>("/api/auth/logout", "POST"), onSuccess: () => qc.clear() });
}
