import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Money } from "../components/Money";
import { PrivacyProvider } from "../lib/privacy";

describe("privacy blur", () => {
  it("adds the blur class when privacy is on", () => {
    localStorage.removeItem("fc.privacyBlur");
    render(
      <PrivacyProvider initial={true}>
        <Money value="1234.56" />
      </PrivacyProvider>,
    );
    expect(screen.getByText("$1,234.56").className).toContain("privacy-blur");
  });
  it("renders plainly when privacy is off", () => {
    localStorage.removeItem("fc.privacyBlur");
    render(
      <PrivacyProvider initial={false}>
        <Money value="75" />
      </PrivacyProvider>,
    );
    expect(screen.getByText("$75.00").className).not.toContain("privacy-blur");
  });
});
