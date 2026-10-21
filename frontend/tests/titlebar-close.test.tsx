import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TitleBar from "@/components/layout/TitleBar";

describe("Electron title bar close control", () => {
  afterEach(() => {
    delete window.electron;
  });

  it("closes the desktop app instead of hiding it in the notification area", () => {
    const close = vi.fn().mockResolvedValue(undefined);
    const hide = vi.fn();
    Object.defineProperty(window, "electron", {
      configurable: true,
      value: {
        isElectron: true,
        window: { close, hide, isMaximized: vi.fn().mockResolvedValue(false) },
      } as unknown as Window["electron"],
    });

    render(<TitleBar />);
    fireEvent.click(screen.getAllByRole("button")[2]);

    expect(close).toHaveBeenCalledOnce();
    expect(hide).not.toHaveBeenCalled();
  });
});
