import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "../app/context/ThemeContext";
import ParticleAccelerator from "../app/components/dashboard/ParticleAccelerator";

describe("ParticleAccelerator", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("pauses its animation while off-screen and resumes when visible", () => {
    let triggerIntersection: ((isIntersecting: boolean) => void) | undefined;
    let disconnected = false;

    class IntersectionObserverMock {
      constructor(callback: IntersectionObserverCallback) {
        triggerIntersection = (isIntersecting) => {
          callback(
            [{ isIntersecting } as IntersectionObserverEntry],
            this as unknown as IntersectionObserver,
          );
        };
      }

      observe() {}
      disconnect() {
        disconnected = true;
      }
    }

    vi.stubGlobal("IntersectionObserver", IntersectionObserverMock);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      {} as CanvasRenderingContext2D,
    );
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockReturnValueOnce(1)
      .mockReturnValueOnce(2);
    const cancelAnimationFrame = vi
      .spyOn(window, "cancelAnimationFrame")
      .mockImplementation(() => {});

    const view = render(
      <ThemeProvider>
        <ParticleAccelerator />
      </ThemeProvider>,
    );

    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);

    act(() => triggerIntersection?.(false));
    expect(cancelAnimationFrame).toHaveBeenCalledWith(1);
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);

    act(() => triggerIntersection?.(true));
    expect(requestAnimationFrame).toHaveBeenCalledTimes(2);

    view.unmount();
    expect(disconnected).toBe(true);
    expect(cancelAnimationFrame).toHaveBeenCalledWith(2);
  });

  it("draws a still frame for reduced motion without scheduling animation frames", () => {
    const gradient = { addColorStop: vi.fn() };
    const context = {
      arc: vi.fn(),
      beginPath: vi.fn(),
      clearRect: vi.fn(),
      createRadialGradient: vi.fn(() => gradient),
      fill: vi.fn(),
      restore: vi.fn(),
      save: vi.fn(),
    };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      context as unknown as CanvasRenderingContext2D,
    );
    const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame");
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );

    const view = render(
      <ThemeProvider>
        <ParticleAccelerator />
      </ThemeProvider>,
    );

    expect(context.clearRect).toHaveBeenCalledOnce();
    expect(requestAnimationFrame).not.toHaveBeenCalled();

    view.unmount();
  });
});
