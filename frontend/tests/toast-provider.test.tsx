import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ToastProvider from "../app/components/layout/ToastProvider";

describe("ToastProvider", () => {
  it("places desktop notifications below the window controls strip", () => {
    const { container } = render(<ToastProvider>App</ToastProvider>);
    const toaster = container.querySelector<HTMLElement>("[data-rht-toaster]");

    expect(toaster?.style.top).toBe("calc(var(--averqel-desktop-chrome-height, 0px) + 16px)");
  });
});
