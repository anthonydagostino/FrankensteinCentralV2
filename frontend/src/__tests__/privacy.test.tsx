import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Money } from "../components/Money";
import { PrivacyProvider, usePrivacy } from "../lib/privacy";

function Toggle() {
  const { toggle } = usePrivacy();
  return (
    <button type="button" onClick={toggle}>
      toggle
    </button>
  );
}

describe("privacy blur", () => {
  it("adds the blur class when privacy is on", () => {
    render(
      <PrivacyProvider initial={true}>
        <Money value="1234.56" />
      </PrivacyProvider>,
    );
    expect(screen.getByText("$1,234.56").className).toContain("privacy-blur");
  });
  it("renders plainly when privacy is off", () => {
    render(
      <PrivacyProvider initial={false}>
        <Money value="75" />
      </PrivacyProvider>,
    );
    expect(screen.getByText("$75.00").className).not.toContain("privacy-blur");
  });
  it("follows the server value when it changes and persists local toggles", () => {
    const persist = vi.fn();
    const view = render(
      <PrivacyProvider initial={false} persist={persist}>
        <Money value="1" />
        <Toggle />
      </PrivacyProvider>,
    );
    act(() => screen.getByText("toggle").click());
    expect(screen.getByText("$1.00").className).toContain("privacy-blur");
    expect(persist).toHaveBeenCalledWith(true);
    view.rerender(
      <PrivacyProvider initial={false} persist={persist}>
        <Money value="1" />
        <Toggle />
      </PrivacyProvider>,
    );
    expect(screen.getByText("$1.00").className).toContain("privacy-blur");
    view.rerender(
      <PrivacyProvider initial={true} persist={persist}>
        <Money value="1" />
        <Toggle />
      </PrivacyProvider>,
    );
    expect(screen.getByText("$1.00").className).toContain("privacy-blur");
  });
});
