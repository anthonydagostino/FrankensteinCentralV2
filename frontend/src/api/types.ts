export type ModuleStatus = "ok" | "degraded" | "error" | "disabled";

export interface Envelope<T> {
  module: string;
  status: ModuleStatus;
  configured: boolean;
  fetched_at: string | null;
  stale: boolean;
  error: string | null;
  data: T | null;
  setup_hint?: string[] | null;
}

// ---- weather
export interface WeatherCurrent {
  temp: number | null;
  feels_like: number | null;
  humidity: number | null;
  code: number | null;
  label: string;
  icon: string;
  is_day: boolean;
  wind_mph: number | null;
  gust_mph: number | null;
  precip_in: number;
}
export interface WeatherHour { time: string; temp: number | null; pop: number; code: number | null; icon: string; wind_mph: number | null }
export interface WeatherDay { date: string; hi: number | null; lo: number | null; pop: number; precip: number; code: number | null; label: string; icon: string; sunrise: string | null; sunset: string | null; uv: number | null; wind_max: number | null }
export interface WeatherAlert { id: string | null; event: string; severity: string; urgency: string | null; headline: string | null; description: string | null; instruction: string | null; effective: string | null; expires: string | null; area: string | null }
export interface WeatherData {
  location: string;
  current: WeatherCurrent;
  next_12h: WeatherHour[];
  daily: WeatherDay[];
  alerts: WeatherAlert[];
  alerts_error?: string;
  badges: string[];
  aqi: number | null;
  available: string[];
  units: "imperial" | "metric";
}

// ---- calendar
export interface CalEvent {
  id: string; title: string; start: string; end: string; all_day: boolean; multi_day: boolean; calendar: string; color: string;
  location: string | null; description: string | null; join_url: string | null; tentative: boolean; in_progress: boolean;
}
export interface CalDay { date: string; label: string; events: CalEvent[] }
export interface NextEvent { title: string; start: string; end: string; minutes_until: number; in_progress: boolean; calendar: string; color: string; join_url: string | null; location: string | null }
export interface CalendarData { now: string; next_event: NextEvent | null; days: CalDay[]; month_density: Record<string, number>; feeds: { name: string; color: string }[] }

// ---- finance
export interface AccountRow { id: string; name: string; type: string; role: string | null; balance: string; owed?: string; balance_date: string | null; url: string | null }
export interface FinanceSummary {
  currency: string; firefly_version: string | null; net_worth: string; mtd_spend: string; last_month_same_day: string; pace: "ahead" | "behind" | null; pace_pct: number | null;
  left_to_spend: string | null; earned_mtd: string | null; bills_unpaid: string | null;
  daily_spend: { date: string; amount: string }[];
  categories: { name: string; amount: string; share: number }[];
  budgets: { id: string; name: string; limit: string; spent: string; pct: number | null; level: "ok" | "warn" | "over" }[];
  bills: { id: string; name: string; amount: string; due: string; days: number; paid: boolean }[];
  accounts: { assets: AccountRow[]; credit_cards: AccountRow[]; liabilities: AccountRow[] };
  freshness: { newest_transaction: string | null; hours_since: number | null; stale: boolean; stale_after_hours: number; per_account: { account_id: string; account: string; newest: string }[] };
  links: Record<string, string>;
  privacy_default: boolean;
}
export interface TransactionRow { journal_id: number; group_id: string; date: string; description: string; amount: string; sign: number; type: string; account: string; counterparty: string | null; category: string | null; url: string | null }

// ---- cards
export interface CardData {
  id: string; label: string; annual_fee: string; account: { id: string; name: string; pinned: boolean } | null; configured: boolean; message?: string;
  balance?: string | null; balance_date?: string | null; credit_limit?: string | null; spend_month?: string; spend_30d?: string;
  largest_purchase?: { description: string; amount: string; date: string } | null;
  last_credit?: { description: string; amount: string; date: string; benefit_id: string | null } | null;
  captured_ytd?: string; fee_offset?: number | null; still_available?: string | null; url?: string | null;
}

// ---- benefits
export type BenefitStatus = "used" | "partial" | "pending" | "unused" | "expired_unused" | "expired_partial" | "manual";
export interface PeriodResult {
  period_key: string; label: string; start: string | null; end: string | null; days_left: number; ended: boolean; cap: string; used: string; pending: string; remaining: string;
  status: BenefitStatus; expiring_soon: boolean; missing_credit: string | null; missing_credit_age_days: number | null; manual_entry: string | null; last_used?: string | null; next_eligible?: string | null;
}
export interface Evidence { journal_id: number; date: string; kind: string; amount: string; description: string; period_key: string | null; confidence: string | null; matched_purchase: number | null; attribution: string | null; override: boolean; over_cap: boolean; note: string | null; refunded?: string; credited?: string }
export interface BenefitOut { id: string; name: string; tracking: "matched" | "credits_only" | "manual"; period: string; cap: string; enrollment_required: boolean; active_from: string | null; active_until: string | null; notes: string; current: PeriodResult | null; history: PeriodResult[]; evidence: Evidence[] }
export interface BenefitCard { card: string; label: string; annual_fee: string; account: { id: string; name: string } | null; captured_ytd: string; fee_offset: number | null; left_on_table_ytd: string; still_available: string; benefits: BenefitOut[] }
export interface BenefitsData { year: number; today: string; catalog_last_verified: string; cards: BenefitCard[]; expiring_soon: { card: string; card_label: string; id: string; name: string; remaining: string; days_left: number }[]; missing_credits: { card: string; card_label: string; id: string; name: string; message: string }[] }
export interface UnclassifiedItem { card: string; journal_id: number; group_id: string; date: string; amount: string; description: string; account: string; kind: string; benefit_id: string | null; confidence: string | null; note: string | null; suggested_pattern: string }
export interface OverrideRow { id: number; firefly_journal_id: number; classification: string; benefit_id: string | null; period_key: string | null; note: string | null; created_at: string }
export interface UnclassifiedData { items: UnclassifiedItem[]; overrides: OverrideRow[]; benefits: { id: string; name: string; card: string }[] }

// ---- plex
export interface PlexSession { session_key: string | null; rating_key: string; type: string; title: string; subtitle: string | null; thumb: string | null; user: string | null; player: string | null; state: string; progress: number; transcoding: boolean }
export interface PlexItem { rating_key: string; type: string; title: string; subtitle: string | null; year: number | null; thumb: string | null; added_at: string | null; progress: number | null }
export interface PlexData { server: { online: boolean; version: string | null; machine_id: string | null; name: string | null }; sessions: PlexSession[]; recently_added: PlexItem[]; on_deck: PlexItem[]; libraries: { key: string; title: string; type: string; count: number | null }[]; links: { server: string; item_template: string } }

// ---- vault
export interface VaultData { online: boolean; latency_ms: number | null; version: string | null; error: string | null; checked_at: string; backup: { available: boolean; newest_file?: string | null; age_hours?: number | null; error?: string } | null; public_url: string | null; admin_url: string | null }

// ---- containers
export interface ContainerRow { id: string; short_id: string; name: string; display_name: string; image: string | null; state: string; status: string; health: string; uptime_seconds: number | null; started_at: string | null; restart_count: number | null; restart_increased: boolean; exit_code: number | null; url: string | null; critical: boolean; hidden: boolean; project: string | null; service: string | null; ports: string[] }
export interface ContainersData { summary: { total: number; running: number; stopped: number; paused: number; restarting: number; unhealthy: number; server_version: string | null; engine_total: number | null }; groups: { project: string; containers: ContainerRow[] }[]; restart_allowed: boolean; portainer_url: string | null; generated_at: string }

// ---- probes and attention
export interface ProbesData { probes: { name: string; url: string | null; ok: boolean; status_code: number | null; latency_ms: number | null; error: string | null }[]; checked_at: string }
export interface AttentionItem { severity: "critical" | "warning" | "info"; icon: string; title: string; detail: string | null; link: string | null; source: string; time: string | null }
export interface AttentionData { items: AttentionItem[] }

// ---- config, status, settings
export interface PublicConfig {
  owner_name: string; timezone: string; locations: { name: string; default: boolean }[]; selected_location: string; units: string;
  links: { name: string; url: string; icon: string }[]; cards: { id: string; label: string }[];
  ui: { theme: string; accent: string; kiosk_rotate_seconds: number };
  privacy: { hide_amounts_by_default: boolean; kiosk_hide_amounts: boolean };
  features: { finance_sync: boolean; docker_restart: boolean; writeback_tags: boolean; kiosk: boolean; mock_mode: boolean };
  auth: { password_configured: boolean };
  catalog_last_verified: string; currency: string;
}
export interface StatusRow { module: string; status: ModuleStatus; configured: boolean; fetched_at: string | null; last_attempt: string | null; stale: boolean; error: string | null; interval: number; mocked: boolean | null; setup_hint: string[] }
export interface SettingsData { values: Record<string, string>; card_accounts: Record<string, { id: string; name: string; type: string; role: string | null; pinned: boolean } | null>; accounts: { id: string; name: string; type: string; role: string | null }[]; catalog_last_verified: string }
export interface Me { authenticated: boolean; mode: "session" | "kiosk" | null; read_only: boolean }

// ---- recurring charges
export interface RecurringItem {
  key: string; name: string; merchant: string | null; account: string | null; category: string | null;
  cadence: "weekly" | "biweekly" | "monthly" | "bimonthly" | "quarterly" | "semiannual" | "annual";
  interval_days: number; amount: string; previous_amount: string | null; amount_min: string; amount_max: string; variable: boolean;
  occurrences: number; first_seen: string; last_seen: string; next_expected: string; days_until_next: number;
  monthly_cost: string; annual_cost: string; status: "active" | "lapsed"; new: boolean; price_increase: boolean; passthrough: boolean; ignored: boolean; url: string | null;
}
export interface RecurringData {
  items: RecurringItem[];
  totals: { monthly_total: string; annual_total: string; active_count: number; new_count: number; increased_count: number; lapsed_count: number; ignored_count: number };
  today: string;
}
