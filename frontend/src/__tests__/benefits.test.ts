import { describe, expect, it } from "vitest";
import type { BenefitOut, PeriodResult } from "../api/types";
import { sortBenefits, statusTone } from "../lib/benefits";

function benefit(id: string, current: Partial<PeriodResult> | null): BenefitOut {
  const period = current
    ? ({
        period_key: "2026-M11",
        label: "November 2026",
        cap: "10.00",
        used: "0.00",
        pending: "0.00",
        remaining: "10.00",
        status: "unused",
        expiring_soon: false,
        days_left: 10,
        ...current,
      } as PeriodResult)
    : null;
  return {
    id,
    name: id,
    card: "amex_gold",
    period: "monthly",
    tracking: "matched",
    cap: "10.00",
    enrollment_required: false,
    notes: "",
    active_from: null,
    active_until: null,
    current: period,
    history: [],
    evidence: [],
  } as unknown as BenefitOut;
}

describe("sortBenefits", () => {
  it("puts expiring first, then by status, then by remaining, with history-only last", () => {
    const sorted = sortBenefits([
      benefit("used", { status: "used", remaining: "0.00" }),
      benefit("none", null),
      benefit("unused-small", { status: "unused", remaining: "5.00" }),
      benefit("expiring", { status: "partial", expiring_soon: true }),
      benefit("unused-big", { status: "unused", remaining: "50.00" }),
      benefit("pending", { status: "pending" }),
    ]).map((b) => b.id);
    expect(sorted).toEqual(["expiring", "pending", "unused-big", "unused-small", "used", "none"]);
  });
  it("maps statuses to chip tones", () => {
    expect(statusTone("used")).toBe("good");
    expect(statusTone("pending")).toBe("warn");
    expect(statusTone("partial")).toBe("info");
    expect(statusTone("expired_unused")).toBe("bad");
    expect(statusTone("manual")).toBe("neutral");
  });
});
