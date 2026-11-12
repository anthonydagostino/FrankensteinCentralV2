import type { BulkState, FitnessWeight, Muscle, StrengthExercise, VolumeMuscle, VolumeZone, WeightBand } from "../api/types";
import type { ChipTone } from "../components/Bars";

/** The fixed muscle order used everywhere, matching the backend. */
export const MUSCLES: Muscle[] = ["chest", "back", "shoulders", "biceps", "triceps", "quads", "hamstrings", "glutes", "calves", "abs"];

export const FITNESS_VIEWS = ["weight", "consistency", "volume", "strength", "stalled"] as const;
export type FitnessView = (typeof FITNESS_VIEWS)[number];

export const isFitnessView = (value: string | undefined): value is FitnessView => FITNESS_VIEWS.includes(value as FitnessView);

export const VIEW_TITLE: Record<FitnessView, string> = {
  weight: "Weight",
  consistency: "Consistency",
  volume: "Volume",
  strength: "Strength",
  stalled: "Stalled",
};

/** The "What this is" and "Why it matters" copy at the top of every detail view. */
export const VIEW_COPY: Record<FitnessView, { what: string; why: string }> = {
  weight: {
    what: "Your scale weight jumps around day to day from water, salt and food volume. The trend line smooths that out so you can see your real direction. The rate shows how fast you are gaining.",
    why: "On a lean bulk, gaining too slowly means leaving muscle on the table, and gaining too fast mostly adds fat. Staying in the band keeps the gain mostly muscle. The bulk quality chart checks whether added weight is coming with added strength.",
  },
  consistency: {
    what: "How often you actually trained versus your target, and how long each muscle has gone without work.",
    why: "Showing up is the biggest driver of results. This catches missed weeks and neglected muscles before they add up.",
  },
  volume: {
    what: "The number of sets each muscle got this week. Sets where the muscle is the main target count as 1, and sets where it only assists count as 0.5.",
    why: "Weekly sets per muscle is the best-supported predictor of muscle growth. Under 4 is too little to grow, 10 to 20 is the target range, and past 20 the returns shrink. This shows which muscles are under-trained.",
  },
  strength: {
    what: "Estimated one-rep max (e1RM) converts any set into the weight you could likely lift once, so sets with different weights and reps can be compared on one line. A PR is any set that beats what you have done before.",
    why: "Muscle growth requires doing more over time. A rising e1RM line is proof of progressive overload. A flat line means something needs to change.",
  },
  stalled: {
    what: "Lifts whose estimated max has not improved over the last 6 weeks.",
    why: "A stall on one lift usually means that exercise needs a change in reps, load or variation. Stalls on many lifts at once usually point to food, sleep or recovery.",
  },
};

export const COLLECTING_DAYS = 14;

const ZONE_HEX: Record<VolumeZone, string> = { below_minimum: "#f87171", building: "#fbbf24", target: "#4ade80", high: "#60a5fa" };
const ZONE_BG: Record<VolumeZone, string> = { below_minimum: "bg-red-400", building: "bg-amber-400", target: "bg-accent", high: "bg-sky-400" };
const ZONE_TONE: Record<VolumeZone, ChipTone> = { below_minimum: "bad", building: "warn", target: "good", high: "info" };
const ZONE_LABEL: Record<VolumeZone, string> = { below_minimum: "below minimum", building: "building", target: "target", high: "high" };

export const zoneColor = (zone: VolumeZone): string => ZONE_HEX[zone];
export const zoneClass = (zone: VolumeZone): string => ZONE_BG[zone];
export const zoneTone = (zone: VolumeZone): ChipTone => ZONE_TONE[zone];
export const zoneLabel = (zone: VolumeZone): string => ZONE_LABEL[zone];

const BAND_TONE: Record<WeightBand, ChipTone> = { below: "warn", in: "good", above: "bad" };
const BAND_LABEL: Record<WeightBand, string> = { below: "below band", in: "in band", above: "above band" };
export const bandTone = (band: WeightBand): ChipTone => BAND_TONE[band];
export const bandLabel = (band: WeightBand): string => BAND_LABEL[band];

const BULK_TONE: Record<BulkState, ChipTone> = { on_track: "good", gaining_without_strength: "bad", recomping: "info", under_eating: "warn" };
export const bulkTone = (state: BulkState): ChipTone => BULK_TONE[state];

/** "+0.4", "-1.2", "0.0"; null or undefined gives an empty string. */
export function signed(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "";
  const text = Math.abs(n).toFixed(digits);
  if (n > 0) return `+${text}`;
  if (n < 0) return `-${text}`;
  return text;
}

/** "12" for whole numbers, "12.5" otherwise. */
export const formatSets = (sets: number): string => (Number.isInteger(sets) ? String(sets) : sets.toFixed(1));

export const titleCase = (word: string): string => word.charAt(0).toUpperCase() + word.slice(1);

/** The one line summary on the dashboard tile: "156.2 lb, +0.4 lb/wk, in band" or the collecting state. */
export function weightSummary(weight: FitnessWeight): string {
  if (weight.status === "collecting") return `collecting data (${weight.days_of_data} of ${COLLECTING_DAYS} days)`;
  if (!weight.trend) return "no weigh-ins";
  const parts = [`${weight.trend.lb.toFixed(1)} lb`];
  if (weight.rate) parts.push(`${signed(weight.rate.lb_per_week)} lb/wk`, bandLabel(weight.rate.band));
  return parts.join(", ");
}

/** Tooltip for one muscle on the volume strip: "chest 12.5 sets, target". */
export const muscleTitle = (m: VolumeMuscle): string => `${m.muscle} ${formatSets(m.sets)} sets, ${zoneLabel(m.zone)}`;

/** Background class for a heatmap cell by how many sessions happened that day. */
export function heatmapClass(sessions: number): string {
  if (sessions <= 0) return "bg-ink-800";
  if (sessions === 1) return "bg-accent/40";
  if (sessions === 2) return "bg-accent/70";
  return "bg-accent";
}

/** Splits the 84 day heatmap (oldest first, starting on a Monday) into weeks of seven days. */
export function chunkWeeks<T>(cells: T[], size = 7): T[][] {
  const weeks: T[][] = [];
  for (let i = 0; i < cells.length; i += size) weeks.push(cells.slice(i, i + size));
  return weeks;
}

/** The exercise with the most sessions; ties keep the first in list order. */
export function defaultExerciseKey(exercises: StrengthExercise[]): string {
  let best: StrengthExercise | undefined;
  for (const e of exercises) if (!best || e.sessions > best.sessions) best = e;
  return best?.exercise_key ?? "";
}

/** Fixed line colors for the eight week volume chart, one per muscle in the fixed order. */
export const MUSCLE_COLORS: Record<Muscle, string> = {
  chest: "#f87171",
  back: "#60a5fa",
  shoulders: "#fbbf24",
  biceps: "#c084fc",
  triceps: "#f472b6",
  quads: "#4ade80",
  hamstrings: "#2dd4bf",
  glutes: "#fb923c",
  calves: "#a3e635",
  abs: "#97a69c",
};

/** The widest value a volume bar can show so the 20 set boundary always has room to the right of it. */
export const volumeScaleMax = (muscles: VolumeMuscle[], targetMax: number): number => Math.max(targetMax * 1.25, ...muscles.map((m) => m.sets)) || targetMax;
