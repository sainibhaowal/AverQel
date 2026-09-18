import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DeepSpaceComposer from "../app/dashboard/deepspace/_components/DeepSpaceComposer";

describe("DeepSpaceComposer active-turn controls", () => {
  it("keeps the draft editable and exposes queue, steer, stop, and removal actions", () => {
    const onSubmit = vi.fn();
    const onStop = vi.fn();
    const onSteer = vi.fn();
    const onCancelQueuedTurn = vi.fn();

    render(
      <DeepSpaceComposer
        query="Use the second file instead"
        isStreaming
        onQueryChange={vi.fn()}
        onSubmit={onSubmit}
        onStop={onStop}
        onSteer={onSteer}
        queuedTurns={[
          {
            clientRequestId: "queued-1",
            prompt: "Summarize the next document",
            status: "queued",
          },
        ]}
        onCancelQueuedTurn={onCancelQueuedTurn}
      />,
    );

    expect(screen.getByPlaceholderText("Message DeepSpace...")).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Queue message" }));
    fireEvent.click(screen.getByRole("button", { name: "Stop response" }));
    fireEvent.click(screen.getByRole("button", { name: "Steer" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove queued message 1" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onStop).toHaveBeenCalledOnce();
    expect(onSteer).toHaveBeenCalledOnce();
    expect(onCancelQueuedTurn).toHaveBeenCalledWith("queued-1");
  });
});
