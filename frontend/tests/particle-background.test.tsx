import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ParticleBackground from "../app/components/marketing/ParticleBackground";

describe("ParticleBackground", () => {
  it("draws a still frame without starting a continuous loop for reduced motion", () => {
    const gradient = { addColorStop: vi.fn() };
    const context = {
      arc: vi.fn(),
      beginPath: vi.fn(),
      bezierCurveTo: vi.fn(),
      createRadialGradient: vi.fn(() => gradient),
      drawImage: vi.fn(),
      fill: vi.fn(),
      fillRect: vi.fn(),
      moveTo: vi.fn(),
      stroke: vi.fn(),
    };
    const getContext = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(context as unknown as CanvasRenderingContext2D);
    const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame");
    const matchMedia = vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    vi.stubGlobal("matchMedia", matchMedia);

    const { unmount } = render(<ParticleBackground />);

    expect(getContext).toHaveBeenCalledTimes(2);
    expect(context.fillRect).toHaveBeenCalled();
    expect(requestAnimationFrame).not.toHaveBeenCalled();

    unmount();
    getContext.mockRestore();
    requestAnimationFrame.mockRestore();
    vi.unstubAllGlobals();
  });

  it("builds the grain texture once and reuses it across animation frames", () => {
    const gradient = { addColorStop: vi.fn() };
    const grainContext = { fillRect: vi.fn() };
    const context = {
      arc: vi.fn(),
      beginPath: vi.fn(),
      bezierCurveTo: vi.fn(),
      createRadialGradient: vi.fn(() => gradient),
      drawImage: vi.fn(),
      fill: vi.fn(),
      fillRect: vi.fn(),
      moveTo: vi.fn(),
      stroke: vi.fn(),
    };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValueOnce(context as unknown as CanvasRenderingContext2D)
      .mockReturnValueOnce(grainContext as unknown as CanvasRenderingContext2D);
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );

    const view = render(<ParticleBackground />);
    expect(grainContext.fillRect).toHaveBeenCalledTimes(800);

    act(() => frames.shift()?.(16));
    act(() => frames.shift()?.(32));

    expect(context.drawImage).toHaveBeenCalledTimes(2);
    expect(grainContext.fillRect).toHaveBeenCalledTimes(800);
    view.unmount();
  });
});
