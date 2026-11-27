import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  BenefitsData,
  CalendarData,
  ContainersData,
  Envelope,
  FinanceSummary,
  PlexData,
  TrainingData,
  TransitData,
  VaultData,
  WeatherData,
} from "../api/types";
import { Header } from "../components/Header";
import {
  benefitSummary,
  homeGlance,
  moneyGlance,
  readViewMode,
  trainingGlance,
  transitGlance,
  upcomingEvents,
  weatherGlance,
  writeViewMode,
} from "../lib/glance";
import { PrivacyProvider } from "../lib/privacy";
import { GlancePage } from "../pages/Glance";
import { KioskFrame } from "../pages/Kiosk";

const NOW = new Date("2026-11-12T14:00:00Z"); // 9:00 AM New York

function env<T>(module: string, data: T, extra: Partial<Envelope<T>> = {}): Envelope<T> {
  return { module, status: "ok", configured: true, fetched_at: NOW.toISOString(), stale: false, error: null, data, setup_hint: null, ...extra };
}

const calendar: CalendarData = {
  now: NOW.toISOString(),
  next_event: null,
  month_density: {},
  feeds: [],
  days: [
    {
      date: "2026-11-12",
      label: "Thu",
      events: [
        {
          id: "past",
          title: "Morning run",
          start: "2026-11-12T12:30:00Z",
          end: "2026-11-12T13:00:00Z",
          all_day: false,
          multi_day: false,
          calendar: "p",
          color: "#0f0",
          location: null,
          description: null,
          join_url: null,
          tentative: false,
          in_progress: false,
        },
        {
          id: "now",
          title: "Standup",
          start: "2026-11-12T13:45:00Z",
          end: "2026-11-12T14:15:00Z",
          all_day: false,
          multi_day: false,
          calendar: "p",
          color: "#0f0",
          location: null,
          description: null,
          join_url: null,
          tentative: false,
          in_progress: true,
        },
        {
          id: "allday",
          title: "Trash day",
          start: "2026-11-12",
          end: "2026-11-13",
          all_day: true,
          multi_day: false,
          calendar: "p",
          color: "#0f0",
          location: null,
          description: null,
          join_url: null,
          tentative: false,
          in_progress: false,
        },
      ],
    },
    {
      date: "2026-11-13",
      label: "Fri",
      events: [
        {
          id: "tmrw",
          title: "Dentist",
          start: "2026-11-13T15:00:00Z",
          end: "2026-11-13T16:00:00Z",
          all_day: false,
          multi_day: false,
          calendar: "p",
          color: "#0f0",
          location: null,
          description: null,
          join_url: null,
          tentative: false,
          in_progress: false,
        },
      ],
    },
    { date: "2026-11-14", label: "Sat", events: [] },
  ],
};

const weather: WeatherData = {
  location: "Toms River",
  current: {
    temp: 52.4,
    feels_like: 50,
    humidity: 60,
    code: 1,
    label: "Mostly clear",
    icon: "cloud-sun",
    is_day: true,
    wind_mph: 8,
    gust_mph: null,
    precip_in: 0,
  },
  next_12h: Array.from({ length: 12 }, (_, i) => ({
    time: `2026-11-12T${String(15 + i).padStart(2, "0")}:00:00Z`,
    temp: 50 + i,
    pop: i * 5,
    code: 1,
    icon: "sun",
    wind_mph: 5,
  })),
  daily: [
    { date: "2026-11-12", hi: 58, lo: 41, pop: 10, precip: 0, code: 1, label: "Today", icon: "sun", sunrise: null, sunset: null, uv: 3, wind_max: 10 },
    { date: "2026-11-13", hi: 61, lo: 44, pop: 40, precip: 0.1, code: 61, label: "Fri", icon: "cloud-rain", sunrise: null, sunset: null, uv: 2, wind_max: 12 },
  ],
  alerts: [
    {
      id: "a",
      event: "Wind Advisory",
      severity: "Moderate",
      urgency: null,
      headline: null,
      description: null,
      instruction: null,
      effective: null,
      expires: null,
      area: null,
    },
  ],
  badges: ["Windy"],
  aqi: null,
  available: ["Toms River"],
  units: "imperial",
};

const finance = {
  currency: "USD",
  firefly_version: "6",
  net_worth: "25310.55",
  mtd_spend: "1840.00",
  last_month_same_day: "1600.00",
  pace: "ahead",
  pace_pct: 15.4,
  left_to_spend: null,
  earned_mtd: null,
  bills_unpaid: null,
  daily_spend: [],
  categories: [],
  budgets: [],
  bills: [
    { id: "1", name: "Rent", amount: "1500.00", due: "2026-11-15", days: 3, paid: false },
    { id: "2", name: "Gym", amount: "40.00", due: "2026-11-30", days: 18, paid: false },
    { id: "3", name: "Paid one", amount: "99.00", due: "2026-11-13", days: 1, paid: true },
  ],
  accounts: { assets: [], credit_cards: [], liabilities: [] },
  freshness: { newest_transaction: "2026-11-11", hours_since: 20, stale: false, stale_after_hours: 48, per_account: [] },
  links: {},
  privacy_default: false,
} as FinanceSummary;

const training = {
  version: "0.2.1",
  today: "2026-11-12",
  phase: { key: "x", name: "Ramp", week: 1, deload: false },
  days_until_goal: 200,
  goal_date: "2027-06-01",
  sessions_this_week: 3,
  sessions_planned: 6,
  streak_weeks: 4,
  day_streak: null,
  top_lifts: [],
  streak_min_sessions: 5,
  streak_risk: "at_risk",
  sessions_needed_for_streak: 2,
  days_left_in_week: 4,
  last_session: null,
  next_session: { template_key: "legsA", name: "Legs A" },
  trained_today: false,
  weighed_today: false,
  weight: { latest: null, avg7: null, avg7_prev: null, weekly_change: null, target_weekly_change: 0.5, on_track: null },
  week: ["M", "T", "W", "T", "F", "S", "S"].map((label, i) => ({ date: `2026-11-${9 + i}`, label, done: i < 3, today: i === 3, future: i > 3 })),
  weight_series: null,
  public_url: null,
  generated_at: NOW.toISOString(),
} as TrainingData;

function period(status: string, expiring = false, days_left = 10): BenefitsData["cards"][number]["benefits"][number]["current"] {
  return {
    period_key: "2026-M11",
    label: "November 2026",
    start: "2026-11-01",
    end: "2026-11-30",
    days_left,
    ended: false,
    cap: "10.00",
    used: status === "used" ? "10.00" : "0.00",
    pending: "0.00",
    remaining: status === "used" ? "0.00" : "10.00",
    status: status as never,
    expiring_soon: expiring,
    missing_credit: null,
    missing_credit_age_days: null,
    manual_entry: null,
  };
}
const benefits = {
  year: 2026,
  today: "2026-11-12",
  catalog_last_verified: "2026-10-01",
  expiring_soon: [],
  missing_credits: [],
  cards: [
    {
      card: "amex_gold",
      label: "Gold",
      annual_fee: "325.00",
      account: null,
      captured_ytd: "0",
      fee_offset: 0,
      left_on_table_ytd: "0",
      still_available: "0",
      benefits: [
        {
          id: "a",
          name: "Dining credit",
          tracking: "matched",
          period: "monthly",
          cap: "10",
          enrollment_required: false,
          active_from: null,
          active_until: null,
          notes: "",
          current: period("used"),
          history: [],
          evidence: [],
        },
        {
          id: "b",
          name: "Dunkin",
          tracking: "matched",
          period: "monthly",
          cap: "7",
          enrollment_required: false,
          active_from: null,
          active_until: null,
          notes: "",
          current: period("unused", true, 5),
          history: [],
          evidence: [],
        },
        {
          id: "c",
          name: "Resy",
          tracking: "matched",
          period: "monthly",
          cap: "10",
          enrollment_required: false,
          active_from: null,
          active_until: null,
          notes: "",
          current: period("pending"),
          history: [],
          evidence: [],
        },
        {
          id: "d",
          name: "Retired",
          tracking: "matched",
          period: "monthly",
          cap: "10",
          enrollment_required: false,
          active_from: null,
          active_until: "2025-01-01",
          notes: "",
          current: null,
          history: [],
          evidence: [],
        },
      ],
    },
  ],
} as unknown as BenefitsData;

const plex = {
  server: { online: true, version: "1", machine_id: "m", name: "Absolute Cinema" },
  sessions: [
    {
      session_key: "1",
      rating_key: "r",
      type: "movie",
      title: "Heat",
      subtitle: null,
      thumb: null,
      user: "anthony",
      player: "TV",
      state: "playing",
      progress: 40,
      transcoding: false,
    },
  ],
  recently_added: [],
  on_deck: [],
  libraries: [],
  links: { server: "", item_template: "" },
} as PlexData;
const vault = {
  online: true,
  latency_ms: 10,
  version: "1.33",
  error: null,
  checked_at: NOW.toISOString(),
  backup: null,
  public_url: null,
  admin_url: null,
} as VaultData;
const transit: TransitData = {
  from: { code: "UV", name: "Union" },
  to: { code: "NY", name: "New York Penn Station" },
  via: { code: "NP", name: "Newark Penn Station" },
  outbound: [
    {
      train_id: "5418",
      line: "RVL",
      destination: "New York Penn Station",
      scheduled: "2026-11-12T14:09:00Z",
      departs: "2026-11-12T14:09:00Z",
      delay_min: 0,
      status: "ON TIME",
      state: "on_time",
      track: "2",
      direct: true,
      via: null,
    },
    {
      train_id: "5420",
      line: "RVL",
      destination: "Newark Penn Station",
      scheduled: "2026-11-12T14:31:00Z",
      departs: "2026-11-12T14:37:00Z",
      delay_min: 6,
      status: "ON TIME",
      state: "delayed",
      track: "2",
      direct: false,
      via: "Newark Penn Station",
    },
    {
      train_id: "5400",
      line: "RVL",
      destination: "New York Penn Station",
      scheduled: "2026-11-12T13:50:00Z",
      departs: "2026-11-12T13:50:00Z",
      delay_min: 0,
      status: "DEPARTED",
      state: "departed",
      track: null,
      direct: true,
      via: null,
    },
  ],
  inbound: [
    {
      train_id: "3845",
      line: "NEC",
      destination: "Trenton",
      scheduled: "2026-11-12T14:04:00Z",
      departs: "2026-11-12T14:04:00Z",
      delay_min: 0,
      status: "BOARDING",
      state: "boarding",
      track: "9",
      direct: false,
      via: "Newark Penn Station",
    },
    {
      train_id: "3857",
      line: "NEC",
      destination: "Trenton",
      scheduled: "2026-11-12T15:50:00Z",
      departs: "2026-11-12T15:50:00Z",
      delay_min: 0,
      status: "CANCELLED",
      state: "cancelled",
      track: null,
      direct: false,
      via: "Newark Penn Station",
    },
  ],
  messages: [],
  generated_at: NOW.toISOString(),
};

const containers = {
  summary: { total: 10, running: 9, stopped: 1, paused: 0, restarting: 0, unhealthy: 0, server_version: "29", engine_total: 10 },
  groups: [],
  restart_allowed: false,
  portainer_url: null,
  generated_at: NOW.toISOString(),
} as ContainersData;

describe("glance helpers", () => {
  it("lists what is still ahead, skipping events that already ended, with the day they fall on", () => {
    const events = upcomingEvents(calendar, NOW);
    expect(events.map((e) => e.id)).toEqual(["now", "allday", "tmrw"]);
    expect(events.map((e) => e.day)).toEqual(["today", "today", "tomorrow"]);
    expect(upcomingEvents(calendar, NOW, 1)).toHaveLength(1);
    expect(upcomingEvents(null, NOW)).toEqual([]);
  });
  it("summarizes benefits per card from the current periods only", () => {
    const [gold] = benefitSummary(benefits);
    expect(gold).toMatchObject({ label: "Gold", used: 1, pending: 1, open: 1, total: 3 });
    expect(gold.expiring).toEqual([{ name: "Dunkin", days_left: 5, remaining: "10.00" }]);
    expect(benefitSummary(undefined)).toEqual([]);
  });
  it("reads net worth, pace and the bills due within a week", () => {
    const m = moneyGlance(finance)!;
    expect(m.net_worth).toBe("25310.55");
    expect(m.pace).toBe("15% above last month");
    expect(m.pace_tone).toBe("warn");
    expect(m.bills_count).toBe(1); // Rent; Gym is 18 days out and the paid one does not count
    expect(m.bills_total).toBe(1500);
    expect(m.left_to_spend).toBeNull();
    expect(m.daily).toEqual([]);
    expect(moneyGlance({ ...finance, pace: null, pace_pct: null })!.pace).toBeNull();
  });
  it("picks every other hour and tomorrow for the weather", () => {
    const w = weatherGlance(weather)!;
    expect(w.hours).toHaveLength(5);
    expect(w.hours.map((h) => h.time.slice(11, 13))).toEqual(["15", "17", "19", "21", "23"]);
    expect(w.days).toHaveLength(1);
    expect(w.days[0]).toMatchObject({ date: "2026-11-13", hi: 61, lo: 44, pop: 40 });
    expect(w).toMatchObject({ feels_like: 50, wind_mph: 8, humidity: 60 });
    expect(w.alerts).toBe(1);
  });
  it("compresses training and the home line", () => {
    expect(trainingGlance(training)).toMatchObject({
      sessions: "3 / 6",
      next: "Legs A",
      risk: "at_risk",
      phase: "Ramp wk 1",
      weight: { avg7: null, target: 0.5 },
    });
    expect(homeGlance(plex, vault, containers)).toEqual({
      plex: "Heat for anthony",
      plex_ok: true,
      vault: "online",
      containers: { running: 9, stopped: 1, unhealthy: 0 },
    });
    expect(homeGlance({ ...plex, sessions: [] }, undefined, undefined).plex).toBe("Nothing playing");
    expect(homeGlance({ ...plex, server: { ...plex.server, online: false } }, { ...vault, online: false }, undefined)).toMatchObject({
      plex: "Plex offline",
      vault: "down",
    });
  });
  it("turns the train board into minutes away with a short status", () => {
    const t = transitGlance(transit, NOW)!;
    expect(t).toMatchObject({ from: "Union", to: "New York", via: "Newark" });
    expect(t.outbound.map((r) => [r.train_id, r.minutes, r.label, r.tone])).toEqual([
      ["5418", 9, "on time", "neutral"],
      ["5420", 37, "6 min late", "warn"],
    ]);
    expect(t.inbound.map((r) => [r.minutes, r.label, r.tone])).toEqual([
      [4, "boarding", "good"],
      [110, "cancelled", "bad"],
    ]);
    expect(transitGlance(transit, NOW, 1)!.outbound).toHaveLength(1);
    expect(transitGlance(undefined, NOW)).toBeNull();
  });
  it("remembers the chosen view in this browser", () => {
    writeViewMode("glance");
    expect(readViewMode()).toBe("glance");
    writeViewMode("full");
    expect(readViewMode()).toBe("full");
  });
});

function renderGlance(seed: (qc: QueryClient) => void, path = "/glance") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  seed(qc);
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <PrivacyProvider initial={false}>
          <Routes>
            <Route path="/glance" element={<GlancePage />} />
            <Route path="/" element={<div>FULL DASHBOARD</div>} />
          </Routes>
        </PrivacyProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const seedAll = (qc: QueryClient) => {
  qc.setQueryData(
    ["attention", undefined],
    env("attention", {
      items: [{ severity: "warning", icon: "receipt", title: "Netflix went up", detail: null, link: null, source: "recurring", time: null }],
    }),
  );
  qc.setQueryData(["calendar", 3], env("calendar", calendar));
  qc.setQueryData(["weather", undefined], env("weather", weather));
  qc.setQueryData(["finance"], env("finance", finance));
  qc.setQueryData(["lockin"], env("lockin", training));
  qc.setQueryData(["benefits", undefined], env("benefits", benefits));
  qc.setQueryData(["plex"], env("plex", plex));
  qc.setQueryData(["vault"], env("vault", vault));
  qc.setQueryData(["containers"], env("containers", containers));
  qc.setQueryData(["transit"], env("transit", transit));
};

describe("GlancePage", () => {
  beforeEach(() => {
    writeViewMode("full");
    vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  });
  afterEach(() => vi.useRealTimers());

  it("shows every section with the headline numbers", () => {
    renderGlance(seedAll);
    for (const name of ["Calendar", "Weather", "Money", "Trains", "Lock-In", "Amex benefits", "Home", "Attention"]) {
      expect(screen.getByLabelText(name)).toBeTruthy();
    }
    expect(screen.getByText("Standup")).toBeTruthy();
    expect(screen.getByText("Dentist")).toBeTruthy();
    expect(screen.queryByText("Morning run")).toBeNull();
    expect(screen.getByText("$25,311")).toBeTruthy();
    expect(screen.getByText("15% above last month")).toBeTruthy();
    expect(screen.getByText("3 / 6")).toBeTruthy();
    expect(screen.getByText("Netflix went up")).toBeTruthy();
    expect(screen.getByText("Heat for anthony")).toBeTruthy();
    expect(screen.getByText("Dunkin")).toBeTruthy();
    expect(screen.getByText(/of 3 used/)).toBeTruthy();
    expect(screen.getByText("Union to New York")).toBeTruthy();
    expect(screen.getByText("New York to Union")).toBeTruthy();
    expect(screen.getByText("6 min late")).toBeTruthy();
    expect(screen.getAllByText(/via Newark/).length).toBeGreaterThan(0);
    expect(screen.getByText("cancelled")).toBeTruthy();
  });

  it("handles missing data per section without taking the page down", () => {
    renderGlance((qc) => qc.setQueryData(["finance"], env("finance", null as unknown as FinanceSummary, { status: "error", error: "down" })));
    expect(screen.getByText("No finance data")).toBeTruthy();
    expect(screen.getByText("No calendar data")).toBeTruthy();
    expect(screen.getByText("No training data")).toBeTruthy();
    expect(screen.getByText("No train data")).toBeTruthy();
    expect(screen.getByText("All clear")).toBeTruthy();
  });

  it("the full dashboard button clears the saved choice and leaves the view", () => {
    writeViewMode("glance");
    renderGlance(seedAll);
    fireEvent.click(screen.getByTitle("Switch to the full dashboard"));
    expect(readViewMode()).toBe("full");
    expect(screen.getByText("FULL DASHBOARD")).toBeTruthy();
  });
});

describe("kiosk screen off", () => {
  it("offers the moon only under the kiosk frame, blacks the screen on press, and wakes on a click or key", () => {
    writeViewMode("full");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedAll(qc);
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/kiosk"]}>
          <PrivacyProvider initial={true}>
            <KioskFrame>
              <GlancePage />
            </KioskFrame>
          </PrivacyProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.queryByLabelText("Screen off, click to wake")).toBeNull();
    fireEvent.click(screen.getByLabelText("Screen off"));
    const cover = screen.getByLabelText("Screen off, click to wake");
    expect(cover.className).toContain("bg-black");
    fireEvent.click(cover);
    expect(screen.queryByLabelText("Screen off, click to wake")).toBeNull();
    fireEvent.click(screen.getByLabelText("Screen off"));
    fireEvent.keyDown(window, { key: "a" });
    expect(screen.queryByLabelText("Screen off, click to wake")).toBeNull();
  });
  it("has no moon on the plain glance route", () => {
    renderGlance(seedAll);
    expect(screen.queryByLabelText("Screen off")).toBeNull();
  });
});

describe("Header glance toggle", () => {
  it("saves the choice and navigates to the glance route", () => {
    writeViewMode("full");
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <PrivacyProvider initial={false}>
            <Routes>
              <Route path="/" element={<Header readOnly={false} />} />
              <Route path="/glance" element={<div>GLANCE</div>} />
            </Routes>
          </PrivacyProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByLabelText("Glance view"));
    expect(readViewMode()).toBe("glance");
    expect(screen.getByText("GLANCE")).toBeTruthy();
  });
});
