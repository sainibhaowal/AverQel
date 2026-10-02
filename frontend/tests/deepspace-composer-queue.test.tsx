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

  it("filters models by display name, model id, provider, and quantization", () => {
    const onModelSelect = vi.fn();

    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        modelName="deepseek-v4-pro"
        availableModels={[
          {
            providerId: "lmstudio",
            modelName: "deepseek-v4-pro",
            displayName: "DeepSeek V4 Pro",
            quantization: "Q4_K_M",
          },
          {
            providerId: "openai",
            modelName: "gpt-5-mini",
            displayName: "GPT-5 Mini",
          },
        ]}
        onModelSelect={onModelSelect}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /deepseek-v4-pro/i }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search models" }), {
      target: { value: "q4_k_m" },
    });

    expect(screen.getByRole("button", { name: /deepseek v4 pro/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /gpt-5 mini/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /deepseek v4 pro/i }));
    expect(onModelSelect).toHaveBeenCalledWith("lmstudio", "deepseek-v4-pro");
  });

  it("keeps a failed turn visible and exposes queue resume", () => {
    const onResumeQueue = vi.fn();
    const onRetryFailedTurn = vi.fn();

    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        queuePaused
        queueFailedRequestId="failed-1"
        queuePauseReason="web_search failed: provider unavailable"
        queuedTurns={[
          {
            clientRequestId: "failed-1",
            prompt: "Search the report",
            status: "failed",
            error: "web_search failed: provider unavailable",
          },
        ]}
        onResumeQueue={onResumeQueue}
        onRetryFailedTurn={onRetryFailedTurn}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    expect(screen.getByText("Queue paused")).toBeInTheDocument();
    expect(screen.getAllByText("web_search failed: provider unavailable")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Retry failed & resume" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry checkpoint" }));
    expect(onResumeQueue).toHaveBeenCalledOnce();
    expect(onRetryFailedTurn).toHaveBeenCalledWith("failed-1");
  });
});
