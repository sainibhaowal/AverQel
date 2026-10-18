import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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

  it("keeps the complete thread in a stable layout while an answer streams", () => {
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

    expect(screen.getByText(/^Message 1$/)).toBeInTheDocument();
    expect(screen.getByText(/^Message 80$/)).toBeInTheDocument();
  });

  it("keeps agent timelines in the normal flow while scrolling", () => {
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

    expect(screen.getByText(/^Agent message 1$/)).toBeInTheDocument();
    expect(screen.getByText(/^Agent message 80$/)).toBeInTheDocument();
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
