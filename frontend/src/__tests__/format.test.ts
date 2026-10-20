import { describe, expect, it } from "vitest";
import { formatDateOnly, formatMoney, formatTime, humanDuration, minutesLabel, pct, relativeTime } from "../lib/format";

describe("formatMoney", () => {
  it("formats dollars with two decimals and grouping", () => {
    expect(formatMoney("1234.56")).toBe("$1,234.56");
    expect(formatMoney(75)).toBe("$75.00");
    expect(formatMoney("-12.5")).toBe("-$12.50");
    expect(formatMoney("1850", { whole: true })).toBe("$1,850");
    expect(formatMoney("10", { sign: true })).toBe("+$10.00");
  });
  it("handles empty input", () => {
    expect(formatMoney(null)).toBe("");
    expect(formatMoney("")).toBe("");
  });
});

describe("dates", () => {
  it("formats date only strings without timezone shift", () => {
    expect(formatDateOnly("2026-10-20", "MMM d")).toBe("Oct 20");
    expect(formatDateOnly("2026-01-01", "EEE")).toBe("Thu");
  });
  it("formats times in America/New_York", () => {
    expect(formatTime("2026-10-20T13:00:00Z")).toBe("9:00 AM");
    expect(formatTime("2026-10-20T09:30:00-04:00")).toBe("9:30 AM");
  });
  it("relative time", () => {
    const now = new Date("2026-10-20T12:00:00Z");
    expect(relativeTime("2026-10-20T11:55:00Z", now)).toBe("5 min ago");
    expect(relativeTime("2026-10-20T09:00:00Z", now)).toBe("3 h ago");
    expect(relativeTime(null, now)).toBe("never");
  });
});

describe("helpers", () => {
  it("pct clamps", () => {
    expect(pct("75", "75")).toBe(100);
    expect(pct("10", "0")).toBe(0);
    expect(pct("150", "75")).toBe(100);
  });
  it("durations", () => {
    expect(humanDuration(45)).toBe("45s");
    expect(humanDuration(3700)).toBe("1h 1m");
    expect(humanDuration(90 * 3600)).toBe("3d 18h");
    expect(minutesLabel(42)).toBe("42 min");
    expect(minutesLabel(125)).toBe("2 h 5 min");
  });
});
