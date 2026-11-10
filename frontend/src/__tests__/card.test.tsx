import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Envelope } from "../api/types";
import { Card } from "../components/Card";

function env(overrides: Partial<Envelope<{ n: number }>>): Envelope<{ n: number }> {
  return { module: "x", status: "ok", configured: true, fetched_at: "2026-10-20T12:00:00Z", stale: false, error: null, data: { n: 1 }, setup_hint: [], ...overrides };
}

describe("Card", () => {
  it("shows a skeleton while the first refresh is pending", () => {
    render(
      <Card title="Weather" envelope={env({ data: null, error: "First refresh has not completed yet" })}>
        {(d) => <span>n={d.n}</span>}
      </Card>,
    );
    expect(screen.getByLabelText("Weather").querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.queryByText("n=1")).toBeNull();
  });
  it("shows the setup hint when the module is disabled", () => {
    render(
      <Card title="Plex" envelope={env({ status: "disabled", data: null, setup_hint: ["PLEX_TOKEN"] })}>
        {(d) => <span>n={d.n}</span>}
      </Card>,
    );
    expect(screen.getByText("Plex is not configured")).toBeTruthy();
    expect(screen.getByText("PLEX_TOKEN")).toBeTruthy();
  });
  it("keeps last good data with a notice when degraded, errored, or unreachable", () => {
    const { rerender } = render(
      <Card title="Finance" envelope={env({ status: "degraded", error: "bills: HTTP 500" })}>
        {(d) => <span>n={d.n}</span>}
      </Card>,
    );
    expect(screen.getByText("n=1")).toBeTruthy();
    expect(screen.getByText("Partial data: bills: HTTP 500")).toBeTruthy();
    rerender(
      <Card title="Finance" envelope={env({ status: "error", error: "Firefly unreachable", stale: true })}>
        {(d) => <span>n={d.n}</span>}
      </Card>,
    );
    expect(screen.getByText("n=1")).toBeTruthy();
    expect(screen.getByText("Firefly unreachable")).toBeTruthy();
    expect(screen.getByText(/^stale, /)).toBeTruthy();
    rerender(
      <Card title="Finance" envelope={env({})} error={new Error("Failed to fetch")}>
        {(d) => <span>n=
          {d.n}</span>}
      </Card>,
    );
    expect(screen.getByText("Dashboard unreachable: Failed to fetch")).toBeTruthy();
  });
  it("shows the error state when there is no data at all", () => {
    render(
      <Card title="Vault" envelope={env({ status: "error", error: "boom", data: null })}>
        {(d) => <span>n={d.n}</span>}
      </Card>,
    );
    expect(screen.getByText("boom")).toBeTruthy();
    expect(screen.queryByText("n=1")).toBeNull();
  });
});
