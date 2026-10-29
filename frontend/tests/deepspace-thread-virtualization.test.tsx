import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DeepSpaceThread from "../app/dashboard/deepspace/_components/DeepSpaceThread";

describe("DeepSpaceThread virtualization", () => {
  it("shows measured output speed and TTFT beside the response actions", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "measured-response",
            role: "assistant",
            content: "Measured answer",
            rawContent: "Measured answer",
            createdAt: new Date().toISOString(),
            status: "ready",
            metrics: {
              providerOutputTokens: 51,
              providerGenerationDurationMs: 1200,
              tokensPerSecond: 42.5,
              timeToFirstTokenMs: 1190,
              providerTimeToFirstOutputMs: 480,
            },
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    const performance = screen.getByRole("group", { name: "Response performance" });
    expect(performance).toHaveTextContent("42.5 tok/s");
    expect(performance).toHaveTextContent("TTFT 1.19s");
    expect(performance).toHaveTextContent("Provider 480ms");
    expect(screen.getByLabelText(/provider-reported output tokens/i)).toBeInTheDocument();
  });

  it("shows speed as unavailable when the provider does not report exact usage", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "unavailable-speed-response",
            role: "assistant",
            content: "Answer",
            rawContent: "Answer",
            createdAt: new Date().toISOString(),
            status: "ready",
            metrics: {
              providerOutputTokens: null,
              providerGenerationDurationMs: null,
              tokensPerSecond: null,
              tokensPerSecondUnavailableReason: "usage_missing_for_generation_round",
              timeToFirstTokenMs: 472,
            },
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    const performance = screen.getByRole("group", { name: "Response performance" });
    expect(performance).toHaveTextContent("Tok/s —");
    expect(performance).toHaveTextContent("TTFT 472ms");
    expect(
      screen.getByLabelText(
        /at least one generation round did not report exact output-token usage/,
      ),
    ).toBeInTheDocument();
  });

  it("renders a bounded window from a long mission when scroll metrics are provided", () => {
    const messages = Array.from({ length: 80 }, (_, index) => ({
      id: `msg-${index + 1}`,
      role: "assistant" as const,
      content: `Message ${index + 1}`,
      rawContent: `Message ${index + 1}`,
      createdAt: new Date().toISOString(),
      status: "ready" as const,
    }));

    render(
      <DeepSpaceThread
        messages={messages}
        emptyPrompts={[]}
        scrollMetrics={{
          scrollTop: 7000,
          viewportHeight: 900,
        }}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.queryByText(/^Message 1$/)).not.toBeInTheDocument();
    expect(screen.getByText(/^Message 31$/)).toBeInTheDocument();
    expect(screen.queryByText(/^Message 80$/)).not.toBeInTheDocument();
  });

  it("falls back safely to the tail of the thread when scroll metrics are past the end", () => {
    const messages = Array.from({ length: 32 }, (_, index) => ({
      id: `msg-${index + 1}`,
      role: "assistant" as const,
      content: `Message ${index + 1}`,
      rawContent: `Message ${index + 1}`,
      createdAt: new Date().toISOString(),
      status: "ready" as const,
    }));

    render(
      <DeepSpaceThread
        messages={messages}
        emptyPrompts={[]}
        scrollMetrics={{
          scrollTop: 100000,
          viewportHeight: 900,
        }}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText(/^Message 32$/)).toBeInTheDocument();
    expect(screen.queryByText(/^Message 1$/)).not.toBeInTheDocument();
  });

  it("bounds a long streaming thread and reveals older messages on demand", () => {
    const messages = Array.from({ length: 80 }, (_, index) => ({
      id: `stream-msg-${index + 1}`,
      role: "assistant" as const,
      content: `Message ${index + 1}`,
      rawContent: `Message ${index + 1}`,
      createdAt: new Date().toISOString(),
      status: (index === 79 ? "streaming" : "ready") as "streaming" | "ready",
    }));

    render(
      <DeepSpaceThread
        messages={messages}
        emptyPrompts={[]}
        scrollMetrics={{ scrollTop: 7000, viewportHeight: 900 }}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.queryByText(/^Message 1$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Message 31$/)).not.toBeInTheDocument();
    expect(screen.getByText(/^Message 67$/)).toBeInTheDocument();
    expect(screen.getByText(/^Message 80$/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show older messages" }));

    expect(screen.getByText(/^Message 47$/)).toBeInTheDocument();
    expect(screen.queryByText(/^Message 46$/)).not.toBeInTheDocument();
  });

  it("keeps agent timelines bounded while scrolling and exposes older batches", () => {
    const messages = Array.from({ length: 80 }, (_, index) => ({
      id: `agent-msg-${index + 1}`,
      role: "assistant" as const,
      content: `Agent message ${index + 1}`,
      rawContent: `Agent message ${index + 1}`,
      createdAt: new Date().toISOString(),
      status: "ready" as const,
      agentSteps: [
        {
          id: `step-${index + 1}`,
          type: "thinking" as const,
          status: "completed" as const,
          startedAt: new Date().toISOString(),
          data: { message: "Observed" },
        },
      ],
    }));

    render(
      <DeepSpaceThread
        messages={messages}
        emptyPrompts={[]}
        scrollMetrics={{ scrollTop: 7000, viewportHeight: 900 }}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.queryByText(/^Agent message 1$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Agent message 31$/)).not.toBeInTheDocument();
    expect(screen.getByText(/^Agent message 67$/)).toBeInTheDocument();
    expect(screen.getByText(/^Agent message 80$/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show older messages" }));

    expect(screen.getByText(/^Agent message 47$/)).toBeInTheDocument();
    expect(screen.queryByText(/^Agent message 46$/)).not.toBeInTheDocument();
  });

  it("loads the next server page after the visible page has been revealed", async () => {
    const onLoadOlderMessages = vi.fn(async () => 2);
    const messages = Array.from({ length: 3 }, (_, index) => ({
      id: `page-msg-${index + 1}`,
      role: "assistant" as const,
      content: `Page message ${index + 1}`,
      rawContent: `Page message ${index + 1}`,
      createdAt: new Date().toISOString(),
      status: "ready" as const,
    }));

    render(
      <DeepSpaceThread
        messages={messages}
        hasOlderMessages
        onLoadOlderMessages={onLoadOlderMessages}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));

    await screen.findByText(/Showing the most recent 3 of 3 messages/);
    expect(onLoadOlderMessages).toHaveBeenCalledOnce();
  });

  it("hides the response indicator as soon as any streamed progress begins", () => {
    const { rerender } = render(
      <DeepSpaceThread
        messages={[
          {
            id: "pending-assistant",
            role: "assistant" as const,
            content: "",
            rawContent: "",
            createdAt: new Date().toISOString(),
            status: "streaming" as const,
            agentSteps: [],
            timeline: [],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(
      screen.getByRole("status", { name: "AverQel is preparing a response" }),
    ).toBeInTheDocument();

    rerender(
      <DeepSpaceThread
        messages={[
          {
            id: "pending-assistant",
            role: "assistant" as const,
            content: "Hello",
            rawContent: "Hello",
            createdAt: new Date().toISOString(),
            status: "streaming" as const,
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(
      screen.queryByRole("status", { name: "AverQel is preparing a response" }),
    ).not.toBeInTheDocument();

    rerender(
      <DeepSpaceThread
        messages={[
          {
            id: "pending-assistant",
            role: "assistant" as const,
            content: "",
            rawContent: "",
            createdAt: new Date().toISOString(),
            status: "streaming" as const,
            timeline: [
              {
                id: "thinking-1",
                stepId: "thinking-1",
                turnIndex: 1,
                phase: "thinking",
                type: "thinking" as const,
                title: "Internal Thought",
                status: "running" as const,
                startedAt: new Date().toISOString(),
                details: "Working…",
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(
      screen.queryByRole("status", { name: "AverQel is preparing a response" }),
    ).not.toBeInTheDocument();
  });
});
