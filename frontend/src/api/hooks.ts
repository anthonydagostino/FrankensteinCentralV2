import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getJson, sendJson } from "./client";
import type {
  AttentionData,
  BenefitsData,
  CalendarData,
  CardData,
  ContainersData,
  Envelope,
  FinanceSummary,
  FitnessData,
  FitnessSettings,
  Me,
  MuscleMap,
  MuscleMapInput,
  PlexData,
  ProbesData,
  PublicConfig,
  RecurringData,
  SettingsData,
  StatusRow,
  TrainingData,
  TransactionRow,
  UnclassifiedData,
  VaultData,
  WeatherData,
} from "./types";

const MIN = 60_000;

/** Query keys of every view derived from the Firefly cache; invalidated together after a sync or override. */
const FIREFLY_KEYS = [["finance"], ["transactions"], ["cards"], ["benefits"], ["unclassified"], ["recurring"], ["attention"]] as const;

function invalidateFirefly(qc: ReturnType<typeof useQueryClient>) {
  for (const queryKey of FIREFLY_KEYS) void qc.invalidateQueries({ queryKey });
}

/** Polls one module envelope. Named use* because it wraps useQuery. */
function useEnvelope<T>(key: unknown[], url: string, interval: number, enabled = true) {
  return useQuery<Envelope<T>>({
    queryKey: key,
    queryFn: () => getJson<Envelope<T>>(url),
    refetchInterval: interval,
    enabled,
    staleTime: Math.min(interval, 30_000),
  });
}

const withLocation = (path: string, location?: string) => (location ? `${path}?location=${encodeURIComponent(location)}` : path);

export const useMe = (options: { refetchInterval?: number } = {}) =>
  useQuery<Me>({ queryKey: ["me"], queryFn: () => getJson<Me>("/api/auth/me"), staleTime: 30_000, retry: 2, refetchInterval: options.refetchInterval });
export const usePublicConfig = (enabled = true) =>
  useQuery<PublicConfig>({
    queryKey: ["config"],
    queryFn: () => getJson<PublicConfig>("/api/config/public"),
    staleTime: 5 * MIN,
    refetchInterval: 30 * MIN,
    enabled,
  });

export const useAttention = (location?: string) => useEnvelope<AttentionData>(["attention", location], withLocation("/api/attention", location), MIN);
export const useWeather = (location?: string) => useEnvelope<WeatherData>(["weather", location], withLocation("/api/weather", location), 2 * MIN);
export const useCalendar = (days = 7) => useEnvelope<CalendarData>(["calendar", days], `/api/calendar?days=${days}`, 2 * MIN);
export const useFinance = () => useEnvelope<FinanceSummary>(["finance"], "/api/finance/summary", 5 * MIN);
export const useTransactions = (limit = 15) =>
  useEnvelope<{ transactions: TransactionRow[] }>(["transactions", limit], `/api/finance/transactions?limit=${limit}`, 5 * MIN);
export const useRecurring = () => useEnvelope<RecurringData>(["recurring"], "/api/finance/recurring", 5 * MIN);
export const useCards = () => useEnvelope<{ cards: CardData[] }>(["cards"], "/api/cards", 5 * MIN);
export const useBenefits = (year?: number) => useEnvelope<BenefitsData>(["benefits", year], `/api/benefits${year ? `?year=${year}` : ""}`, 5 * MIN);
export const useUnclassified = (enabled = true) => useEnvelope<UnclassifiedData>(["unclassified"], "/api/benefits/unclassified", 5 * MIN, enabled);
export const usePlex = () => useEnvelope<PlexData>(["plex"], "/api/plex", 30_000);
export const useTraining = () => useEnvelope<TrainingData>(["lockin"], "/api/lockin", 2 * MIN);
export const useFitness = () => useEnvelope<FitnessData>(["fitness"], "/api/fitness", 2 * MIN);
export const useFitnessSettings = () =>
  useQuery<FitnessSettings>({ queryKey: ["fitness-settings"], queryFn: () => getJson<FitnessSettings>("/api/fitness/settings") });
export const useMuscleMap = () => useQuery<MuscleMap>({ queryKey: ["muscle-map"], queryFn: () => getJson<MuscleMap>("/api/fitness/muscle-map") });
export const useVault = () => useEnvelope<VaultData>(["vault"], "/api/vault", MIN);
export const useContainers = () => useEnvelope<ContainersData>(["containers"], "/api/containers", 15_000);
export const useProbes = () => useEnvelope<ProbesData>(["probes"], "/api/probes", MIN);
export const useStatus = () =>
  useQuery<{ integrations: StatusRow[]; mock_mode: boolean }>({ queryKey: ["status"], queryFn: () => getJson("/api/status"), refetchInterval: 30_000 });
export const useSettings = () => useQuery<SettingsData>({ queryKey: ["settings"], queryFn: () => getJson<SettingsData>("/api/settings") });

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, string | null>) => sendJson<{ ok: boolean }>("/api/settings", "POST", { values }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["settings"] });
      void qc.invalidateQueries({ queryKey: ["config"] });
      void qc.invalidateQueries({ queryKey: ["weather"] });
      invalidateFirefly(qc);
    },
  });
}

export function useSaveOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { journal_id: number; classification: string; benefit_id?: string | null; period_key?: string | null; note?: string | null }) =>
      sendJson<{ ok: boolean }>("/api/benefits/overrides", "POST", body),
    onSuccess: () => invalidateFirefly(qc),
  });
}

export function useDeleteOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => sendJson<{ ok: boolean }>(`/api/benefits/overrides/${id}`, "DELETE"),
    onSuccess: () => invalidateFirefly(qc),
  });
}

export function useManualUsage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { benefit_id: string; period_key: string; amount?: string | null; used: boolean; note?: string | null }) =>
      sendJson<{ ok: boolean }>("/api/benefits/manual", "POST", body),
    onSuccess: () => invalidateFirefly(qc),
  });
}

/** Query keys refreshed after a fitness settings or muscle map change. */
function invalidateFitness(qc: ReturnType<typeof useQueryClient>) {
  for (const queryKey of [["fitness"], ["fitness-settings"], ["muscle-map"]]) void qc.invalidateQueries({ queryKey });
}

export function useSaveFitnessSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<FitnessSettings>) => sendJson<FitnessSettings>("/api/fitness/settings", "PUT", body),
    onSuccess: () => invalidateFitness(qc),
  });
}

export function useSaveMuscleEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MuscleMapInput) => sendJson<MuscleMap>("/api/fitness/muscle-map", "PUT", body),
    onSuccess: () => invalidateFitness(qc),
  });
}

export function useRestartContainer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sendJson<{ ok: boolean }>(`/api/containers/${id}/restart`, "POST"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["containers"] }),
  });
}

export function useRecurringIgnore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { key: string; ignore: boolean }) => sendJson<{ ok: boolean }>("/api/finance/recurring/ignore", "POST", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["recurring"] });
      void qc.invalidateQueries({ queryKey: ["attention"] });
    },
  });
}

export function useFinanceSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => sendJson<{ ok: boolean; refresh_in_seconds?: number }>("/api/finance/sync", "POST"),
    // the backend re-reads Firefly 90 s after the importer is triggered; refresh every Firefly view just after
    onSuccess: (result) => setTimeout(() => invalidateFirefly(qc), ((result.refresh_in_seconds ?? 90) + 5) * 1000),
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (password: string) => sendJson<{ ok: boolean }>("/api/auth/login", "POST", { password }),
    onSuccess: () => void qc.invalidateQueries(),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => sendJson<{ ok: boolean }>("/api/auth/logout", "POST"), onSuccess: () => qc.clear() });
}
