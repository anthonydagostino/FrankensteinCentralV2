import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeAll, describe, expect, it } from "vitest";
import type { Envelope, FitnessData, Muscle, VolumeZone } from "../api/types";
import {
  chunkWeeks,
  defaultExerciseKey,
  formatSets,
  heatmapClass,
  isFitnessView,
  muscleTitle,
  MUSCLES,
  signed,
  VIEW_COPY,
  volumeScaleMax,
  weightSummary,
  zoneColor,
  zoneTone,
} from "../lib/fitness";
import { FitnessPage } from "../pages/Fitness";
import { FitnessWidget } from "../widgets/Fitness";

// jsdom has no ResizeObserver; Recharts ResponsiveContainer needs one to mount
beforeAll(() => {
  if (!("ResizeObserver" in globalThis)) {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    Object.assign(globalThis, { ResizeObserver: ResizeObserverStub });
  }
});

// ---- fixture, built to the contract

function isoDaysAgo(n: number, from = "2026-11-12"): string {
  const [y, m, d] = from.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d - n, 12));
  return date.toISOString().slice(0, 10);
}

function zoneFor(sets: number): VolumeZone {
  if (sets < 4) return "below_minimum";
  if (sets < 10) return "building";
  if (sets <= 20) return "target";
  return "high";
}

const SETS: Record<Muscle, number> = { chest: 12.5, back: 14, shoulders: 9, biceps: 6.5, triceps: 11, quads: 10, hamstrings: 3, glutes: 8, calves: 2, abs: 22 };

export function fixture(): FitnessData {
  const series = Array.from({ length: 120 }, (_, i) => {
    const daysAgo = 119 - i;
    const trend = 152 + (i / 119) * 4.2;
    return { date: isoDaysAgo(daysAgo), raw: i % 3 === 1 ? null : Number((trend + (i % 5) * 0.3 - 0.6).toFixed(1)), trend: Number(trend.toFixed(2)) };
  });
  const corridor = Array.from({ length: 59 }, (_, i) => {
    const daysAgo = 28 - i;
    const base = 155.2 + i * 0.04;
    return { date: isoDaysAgo(daysAgo), low: Number(base.toFixed(2)), high: Number((base + 0.6).toFixed(2)) };
  });
  const heatmap = Array.from({ length: 84 }, (_, i) => ({ date: isoDaysAgo(87 - i), sessions: [1, 0, 1, 1, 0, 1, 0][i % 7] }));
  const weeks12 = Array.from({ length: 12 }, (_, i) => ({ week_start: isoDaysAgo(87 - i * 7), sessions: i === 11 ? 4 : 5 + (i % 2) }));
  const weeks8 = Array.from({ length: 8 }, (_, i) => ({
    week_start: isoDaysAgo(59 - i * 7),
    sets: Object.fromEntries(MUSCLES.map((m) => [m, Math.max(0, SETS[m] - (7 - i) * 0.5)])) as Record<Muscle, number>,
  }));
  const points = Array.from({ length: 14 }, (_, i) => ({ date: isoDaysAgo(91 - i * 7), e1rm: 190 + i * 1.6, pr: i % 4 === 3 }));
  return {
    as_of: "2026-11-12",
    units: "lb",
    settings: {
      alpha: 0.1,
      band_low_pct: 1.0,
      band_high_pct: 1.5,
      target_sessions: 6,
      zones: { below_minimum_max: 4, building_max: 10, target_max: 20 },
      plateau_weeks: 6,
      flat_pct: 1.0,
      units: "lb",
    },
    weight: {
      status: "ok",
      days_of_data: 37,
      trend: { date: "2026-11-12", lb: 156.2 },
      rate: { lb_per_week: 0.42, pct_per_month: 1.17, band: "in" },
      change_30d_lb: 1.6,
      change_90d_lb: 4.1,
      series,
      corridor,
    },
    consistency: {
      week_start: "2026-11-09",
      this_week: 4,
      target: 6,
      weeks: weeks12,
      heatmap,
      days_since_muscle: MUSCLES.map((m, i) => ({ muscle: m, days: m === "calves" ? null : i + 1 })),
    },
    volume: {
      week_start: "2026-11-09",
      muscles: MUSCLES.map((m) => ({
        muscle: m,
        sets: SETS[m],
        zone: zoneFor(SETS[m]),
        exercises:
          m === "chest"
            ? [
                { exercise_key: "flat-bench", name: "Flat bench press", sets: 6 },
                { exercise_key: "incline-db", name: "Incline dumbbell press", sets: 6.5 },
              ]
            : [],
      })),
      weeks: weeks8,
      unmapped: [{ exercise_key: "cable-fly", sets: 6 }],
      zones: { below_minimum_max: 4, building_max: 10, target_max: 20 },
    },
    strength: {
      prs_this_week: 3,
      exercises: [
        {
          exercise_key: "flat-bench",
          name: "Flat bench press",
          best_e1rm: 212.5,
          sessions: 14,
          points,
          rep_prs: [
            { weight: 185, reps: 8, date: "2026-10-20" },
            { weight: 165, reps: 12, date: "2026-09-10" },
          ],
        },
        {
          exercise_key: "squat",
          name: "Back squat",
          best_e1rm: 290,
          sessions: 9,
          points: points.slice(0, 9).map((p) => ({ ...p, e1rm: p.e1rm + 80 })),
          rep_prs: [],
        },
      ],
      recent_prs: [
        { date: "2026-11-10", exercise_key: "flat-bench", name: "Flat bench press", kind: "e1rm", weight: 190, reps: 6, e1rm: 228 },
        { date: "2026-11-09", exercise_key: "squat", name: "Back squat", kind: "rep", weight: 245, reps: 8, e1rm: 306.3 },
      ],
    },
    stalled: {
      count: 2,
      window_weeks: 6,
      items: [
        {
          exercise_key: "ez-bar-curl",
          name: "EZ-bar curl",
          pct_change: -1.4,
          sessions: 5,
          sparkline: Array.from({ length: 6 }, (_, i) => ({ date: isoDaysAgo(38 - i * 7), e1rm: 95 - i * 0.2 })),
        },
        {
          exercise_key: "ohp",
          name: "Overhead press",
          pct_change: 0.3,
          sessions: 6,
          sparkline: Array.from({ length: 6 }, (_, i) => ({ date: isoDaysAgo(38 - i * 7), e1rm: 120 + (i % 2) * 0.4 })),
        },
      ],
    },
    bulk_quality: {
      state: "on_track",
      label: "on track",
      weight_change_pct: 1.8,
      strength_change_pct: 3.2,
      weeks: weeks8.map((w, i) => ({ week_start: w.week_start, trend_lb: 153.1 + i * 0.4, strength_index: 100 + i * 0.5 })),
    },
    muscle_map: {
      "flat-bench": { name: "Flat bench press", primary: ["chest"], secondary: ["triceps", "shoulders"] },
      squat: { name: "Back squat", primary: ["quads", "glutes"], secondary: ["hamstrings"] },
    },
  };
}

function envelope(data: FitnessData | null): Envelope<FitnessData> {
  return { module: "fitness", status: "ok", configured: true, fetched_at: "2026-11-12T12:00:00Z", stale: false, error: null, data, setup_hint: [] };
}

function renderTile(data: FitnessData) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["fitness"], envelope(data));
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <FitnessWidget />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderPage(view: string, data: FitnessData | null = fixture(), readOnly = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["fitness"], envelope(data));
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/fitness/${view}`]}>
        <Routes>
          <Route path="/fitness/:view" element={<FitnessPage readOnly={readOnly} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---- tile

describe("FitnessWidget", () => {
  it("renders exactly five linked items in order", () => {
    renderTile(fixture());
    const card = screen.getByLabelText("Fitness");
    const links = within(card).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/fitness/weight",
      "/fitness/consistency",
      "/fitness/volume",
      "/fitness/strength",
      "/fitness/stalled",
    ]);
    expect(within(card).queryAllByRole("button")).toHaveLength(0);
    expect(within(links[0]).getByText("156.2 lb, +0.4 lb/wk, in band")).toBeTruthy();
    expect(within(links[1]).getByText("4 / 6")).toBeTruthy();
    expect(within(links[3]).getByText("3")).toBeTruthy();
    expect(within(links[4]).getByText("2")).toBeTruthy();
  });
  it("draws one bar per muscle in the fixed order with a zone tooltip", () => {
    renderTile(fixture());
    const strip = screen.getByLabelText("Weekly sets per muscle");
    const bars = Array.from(strip.children) as HTMLElement[];
    expect(bars).toHaveLength(10);
    expect(bars[0].title).toBe("chest 12.5 sets, target");
    expect(bars[0].className).toContain("bg-accent");
    expect(bars[6].title).toBe("hamstrings 3 sets, below minimum");
    expect(bars[6].className).toContain("bg-red-400");
    expect(bars[9].className).toContain("bg-sky-400");
  });
  it("drops the stalled row when nothing is stalled", () => {
    const data = fixture();
    data.stalled = { count: 0, window_weeks: 6, items: [] };
    renderTile(data);
    const links = within(screen.getByLabelText("Fitness")).getAllByRole("link");
    expect(links).toHaveLength(4);
    expect(links.map((l) => l.getAttribute("href"))).not.toContain("/fitness/stalled");
  });
  it("shows the collecting state while there are fewer than 14 weigh-in days", () => {
    const data = fixture();
    data.weight = { ...data.weight, status: "collecting", days_of_data: 9, rate: null, change_30d_lb: null, change_90d_lb: null };
    renderTile(data);
    expect(screen.getByText("collecting data (9 of 14 days)")).toBeTruthy();
  });
});

// ---- detail page

describe("FitnessPage", () => {
  for (const view of ["weight", "consistency", "volume", "strength", "stalled"] as const) {
    it(`renders the explainer copy for ${view}`, () => {
      renderPage(view);
      expect(screen.getByText("What this is")).toBeTruthy();
      expect(screen.getByText("Why it matters")).toBeTruthy();
      expect(screen.getByText(VIEW_COPY[view].what)).toBeTruthy();
      expect(screen.getByText(VIEW_COPY[view].why)).toBeTruthy();
    });
  }
  it("collapses the explainer with the chevron", () => {
    renderPage("stalled");
    fireEvent.click(screen.getByRole("button", { name: /About stalled/ }));
    expect(screen.queryByText(VIEW_COPY.stalled.what)).toBeNull();
  });
  it("redirects an unknown view to weight", () => {
    renderPage("nope");
    expect(screen.getByText(VIEW_COPY.weight.what)).toBeTruthy();
  });
  it("shows the weight stats, the bulk quality label, and the collecting empty state", () => {
    const { unmount } = renderPage("weight");
    expect(screen.getByText("156.2 lb")).toBeTruthy();
    expect(screen.getByText("+0.42 lb/wk")).toBeTruthy();
    expect(screen.getByText("in band")).toBeTruthy();
    expect(screen.getByText("on track")).toBeTruthy();
    unmount();
    const data = fixture();
    data.weight = { ...data.weight, status: "collecting", days_of_data: 5, rate: null, change_30d_lb: null, change_90d_lb: null };
    data.bulk_quality = null;
    renderPage("weight", data);
    expect(screen.getByText("Collecting data: 5 of 14 weigh-in days")).toBeTruthy();
    expect(screen.getByText("Not enough data yet")).toBeTruthy();
    expect(screen.queryByText("in band")).toBeNull();
  });
  it("renders the heatmap and the days since list, with never for an untrained muscle", () => {
    renderPage("consistency");
    expect(screen.getByText("never")).toBeTruthy();
    expect(screen.getByText("Calves")).toBeTruthy();
    expect(document.querySelectorAll("span[title*='session']")).toHaveLength(84);
  });
  it("expands a muscle to its exercises and hides map editing when read only", () => {
    const { unmount } = renderPage("volume");
    fireEvent.click(screen.getByRole("button", { name: /Chest/ }));
    expect(screen.getByText("Incline dumbbell press")).toBeTruthy();
    expect(screen.getByText("Edit map")).toBeTruthy();
    expect(screen.getAllByText("Save").length).toBeGreaterThan(0);
    unmount();
    renderPage("volume", fixture(), true);
    expect(screen.queryByText("Edit map")).toBeNull();
    expect(screen.queryByText("Save")).toBeNull();
    expect(screen.getByText("cable-fly")).toBeTruthy();
  });
  it("defaults the strength picker to the exercise with the most sessions and lists recent PRs", () => {
    renderPage("strength");
    expect((screen.getByLabelText("Exercise") as HTMLSelectElement).value).toBe("flat-bench");
    expect(screen.getByText("185 lb")).toBeTruthy();
    expect(screen.getByText("245 x 8")).toBeTruthy();
  });
  it("lists stalled lifts and shows the empty state when none", () => {
    const { unmount } = renderPage("stalled");
    expect(screen.getByText("EZ-bar curl")).toBeTruthy();
    expect(screen.getByText("-1.4%")).toBeTruthy();
    unmount();
    const data = fixture();
    data.stalled = { count: 0, window_weeks: 6, items: [] };
    renderPage("stalled", data);
    expect(screen.getByText("No stalled lifts")).toBeTruthy();
  });
  it("shows an error state when LockIn has not loaded, with the explainer still visible", () => {
    renderPage("weight", null);
    expect(screen.getByText(VIEW_COPY.weight.what)).toBeTruthy();
    expect(screen.getByText("LockIn data has not loaded yet")).toBeTruthy();
  });
});

// ---- helpers

describe("fitness helpers", () => {
  it("formats signed numbers", () => {
    expect(signed(0.42)).toBe("+0.4");
    expect(signed(-1.4)).toBe("-1.4");
    expect(signed(0)).toBe("0.0");
    expect(signed(1.17, 2)).toBe("+1.17");
    expect(signed(null)).toBe("");
  });
  it("summarizes the weight line", () => {
    const w = fixture().weight;
    expect(weightSummary(w)).toBe("156.2 lb, +0.4 lb/wk, in band");
    expect(weightSummary({ ...w, rate: { lb_per_week: -0.2, pct_per_month: -0.5, band: "below" } })).toBe("156.2 lb, -0.2 lb/wk, below band");
    expect(weightSummary({ ...w, status: "collecting", days_of_data: 3 })).toBe("collecting data (3 of 14 days)");
    expect(weightSummary({ ...w, trend: null })).toBe("no weigh-ins");
  });
  it("maps zones to colors, tones, and tooltips", () => {
    expect(zoneColor("below_minimum")).toBe("#f87171");
    expect(zoneTone("building")).toBe("warn");
    expect(zoneTone("target")).toBe("good");
    expect(zoneTone("high")).toBe("info");
    expect(muscleTitle({ muscle: "chest", sets: 12.5, zone: "target", exercises: [] })).toBe("chest 12.5 sets, target");
    expect(muscleTitle({ muscle: "abs", sets: 22, zone: "high", exercises: [] })).toBe("abs 22 sets, high");
  });
  it("formats sets and heatmap shades", () => {
    expect(formatSets(6)).toBe("6");
    expect(formatSets(6.5)).toBe("6.5");
    expect(heatmapClass(0)).toBe("bg-ink-800");
    expect(heatmapClass(3)).toBe("bg-accent");
  });
  it("chunks the heatmap into weeks and picks the default exercise", () => {
    expect(chunkWeeks(Array.from({ length: 84 }, (_, i) => i)).map((w) => w.length)).toEqual(Array(12).fill(7));
    expect(defaultExerciseKey(fixture().strength.exercises)).toBe("flat-bench");
    expect(defaultExerciseKey([])).toBe("");
  });
  it("validates views and scales the volume bars", () => {
    expect(isFitnessView("volume")).toBe(true);
    expect(isFitnessView("nope")).toBe(false);
    expect(isFitnessView(undefined)).toBe(false);
    expect(volumeScaleMax(fixture().volume.muscles, 20)).toBe(25);
    expect(volumeScaleMax([{ muscle: "abs", sets: 40, zone: "high", exercises: [] }], 20)).toBe(40);
  });
});
