import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { AttentionItem } from "../api/types";
import { PrivacyProvider } from "../lib/privacy";
import { AttentionStrip } from "../widgets/Attention";

const items: AttentionItem[] = [
  { severity: "warning", icon: "receipt", title: "Netflix went up to $17.99", detail: "Was $15.49 per month", link: "/finance", source: "recurring", time: null },
  { severity: "critical", icon: "cloud-lightning", title: "Tornado Warning", detail: "until 5 PM", link: null, source: "weather", time: null },
];

describe("AttentionStrip", () => {
  it("blurs money sources only when privacy is on", () => {
    const qc = new QueryClient();
    qc.setQueryData(["attention", undefined], { module: "attention", status: "ok", configured: true, fetched_at: null, stale: false, error: null, data: { items }, setup_hint: [] });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <PrivacyProvider initial={true}>
            <AttentionStrip />
          </PrivacyProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("Netflix went up to $17.99").className).toContain("privacy-blur");
    expect(screen.getByText("Was $15.49 per month").className).toContain("privacy-blur");
    expect(screen.getByText("Tornado Warning").className).not.toContain("privacy-blur");
  });
});
