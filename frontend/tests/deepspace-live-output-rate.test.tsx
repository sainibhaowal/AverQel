import React, { act } from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DeepSpaceLiveOutputRate from "../app/dashboard/deepspace/_components/DeepSpaceLiveOutputRate";

describe("DeepSpace live output rate", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("refreshes the rate locally while streaming and stops its timer afterward", async () => {
    vi.useFakeTimers();
    const startedAtMs = new Date("2026-10-20T10:00:00.000Z").getTime();
    vi.setSystemTime(startedAtMs + 1000);

    const view = render(
      <DeepSpaceLiveOutputRate
        outputTokens={10}
        startedAtMs={startedAtMs}
      />,
    );

    expect(screen.getByText(/10\.0 tok\/s/)).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(screen.getByText(/5\.0 tok\/s/)).toBeInTheDocument();

    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
