import { describe, expect, it } from "vitest";
import { awaitingFirstRefresh } from "../api/hooks";

describe("awaitingFirstRefresh", () => {
  const base = { module: "weather", configured: true, stale: false, data: null, setup_hint: null };
  it("is true only for the error envelope the backend sends before its first refresh", () => {
    expect(awaitingFirstRefresh({ ...base, status: "error", fetched_at: null, error: "First refresh has not completed yet" })).toBe(true);
    expect(awaitingFirstRefresh({ ...base, status: "error", fetched_at: "2026-11-12T14:00:00Z", error: "upstream down" })).toBe(false);
    expect(awaitingFirstRefresh({ ...base, status: "ok", fetched_at: "2026-11-12T14:00:00Z", error: null })).toBe(false);
    expect(awaitingFirstRefresh(undefined)).toBe(false);
  });
});
