import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "../components/Modal";

describe("Modal", () => {
  it("Escape closes only the top modal", () => {
    const closeOuter = vi.fn();
    const closeInner = vi.fn();
    render(
      <Modal title="Outer" onClose={closeOuter}>
        <Modal title="Inner" onClose={closeInner}>
          <p>hi</p>
        </Modal>
      </Modal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(closeInner).toHaveBeenCalledTimes(1);
    expect(closeOuter).not.toHaveBeenCalled();
  });
});
