import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DeepSpaceScrollTracker from "../app/dashboard/query/_components/DeepSpaceScrollTracker";
import type { QueryThreadMessage } from "../app/dashboard/query/_lib/stream-protocol";

describe("deepspace scroll tracker", () => {
  beforeEach(() => {
    let instances = 0;
    let disconnects = 0;

    class IntersectionObserverMock {
      constructor() {
        instances += 1;
      }

      observe() {}
      disconnect() {
        disconnects += 1;
      }
      unobserve() {}
    }

    Object.defineProperty(window, "IntersectionObserver", {
      configurable: true,
      writable: true,
      value: IntersectionObserverMock,
    });
    Object.defineProperty(window, "__deepspaceScrollTrackerObserverStats", {
      configurable: true,
      writable: true,
      value: {
        get instances() {
          return instances;
        },
        get disconnects() {
          return disconnects;
        },
      },
    });
  });

  it("renders clickable jump buttons for messages", () => {
    const scrollIntoView = vi.fn();
    const container = document.createElement("div");
    const message = document.createElement("div");
    message.setAttribute("data-message-id", "assistant-1");
    message.scrollIntoView = scrollIntoView;
    container.appendChild(message);

    render(
      <DeepSpaceScrollTracker
        messages={[
          {
            id: "assistant-1",
            role: "assistant",
            content: "Answer",
            rawContent: "Answer",
            createdAt: new Date().toISOString(),
            status: "ready",
          },
        ]}
        scrollContainerRef={{ current: container }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /answer 1: answer/i }));

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
      inline: "nearest",
    });
  });

  it("keeps the marker list internally scrollable so the insert action remains visible", () => {
    const container = document.createElement("div");
    const messages = Array.from({ length: 40 }, (_, index) => ({
      id: `assistant-${index}`,
      role: "assistant" as const,
      content: `Answer ${index}`,
      rawContent: `Answer ${index}`,
      createdAt: new Date().toISOString(),
      status: "ready" as const,
    }));

    render(
      <DeepSpaceScrollTracker
        messages={messages}
        scrollContainerRef={{ current: container }}
        onInsertActiveAnswer={() => {}}
      />,
    );

    expect(screen.getByLabelText(/deepspace message navigation/i)).toHaveClass("overflow-y-auto");
    expect(screen.getByLabelText(/deepspace message navigation/i)).toHaveClass(
      "[scrollbar-width:none]",
    );
    expect(screen.getByRole("button", { name: /insert focused output/i })).toHaveClass("shrink-0");
  });

  it("does not rebuild the observer when only message content changes", () => {
    const container = document.createElement("div");
    const scrollContainerRef = { current: container };
    const windowWithStats = window as Window & {
      __deepspaceScrollTrackerObserverStats?: {
        instances: number;
        disconnects: number;
      };
    };
    const { rerender } = render(
      <DeepSpaceScrollTracker
        messages={[
          {
            id: "assistant-1",
            role: "assistant",
            content: "Answer v1",
            rawContent: "Answer v1",
            createdAt: new Date().toISOString(),
            status: "ready",
          },
        ]}
        scrollContainerRef={scrollContainerRef}
      />,
    );

    const stats = windowWithStats.__deepspaceScrollTrackerObserverStats;

    expect(stats?.instances ?? 0).toBe(1);
    expect(stats?.disconnects ?? 0).toBe(0);

    rerender(
      <DeepSpaceScrollTracker
        messages={[
          {
            id: "assistant-1",
            role: "assistant",
            content: "Answer v2",
            rawContent: "Answer v2",
            createdAt: new Date().toISOString(),
            status: "ready",
          },
        ]}
        scrollContainerRef={scrollContainerRef}
      />,
    );

    expect(stats?.instances ?? 0).toBe(1);
    expect(stats?.disconnects ?? 0).toBe(0);
  });

  it("lazily assembles structured content when inserting the focused answer", () => {
    const onInsertActiveAnswer = vi.fn();
    const container = document.createElement("div");
    const message: QueryThreadMessage = {
      id: "assistant-structured-1",
      role: "assistant",
      content: "Answer",
      rawContent: "Answer",
      createdAt: new Date().toISOString(),
      status: "ready",
      citations: [],
      blocks: [
        {
          id: "chart-1",
          type: "chart",
          title: "Revenue",
          chart_type: "bar",
          series: [{ label: "Q1", value: 42 }],
          raw_payload: null,
          parser_source: "structured",
          x_key: "label",
          y_key: "value",
        },
        {
          id: "diagram-1",
          type: "diagram",
          title: "Flow",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart TD\nA-->B",
        },
        {
          id: "table-1",
          type: "table",
          title: "Metrics",
          headers: ["Quarter", "Value"],
          rows: [["Q1", "42"]],
        },
      ],
      artifacts: [],
      trace: null,
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      thinkingContent: "",
      confidence: undefined,
      traceId: undefined,
      cached: false,
      structured: null,
      error: null,
      activeVersionId: null,
      activeVersionIndex: 0,
      versionCount: 0,
      versions: [],
    };

    render(
      <DeepSpaceScrollTracker
        messages={[message]}
        scrollContainerRef={{ current: container }}
        onInsertActiveAnswer={onInsertActiveAnswer}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /insert focused output/i }));

    expect(onInsertActiveAnswer).toHaveBeenCalledTimes(1);
    expect(onInsertActiveAnswer.mock.calls[0]?.[0]).toContain("Answer");
    expect(onInsertActiveAnswer.mock.calls[0]?.[0]).toContain('"title": "Revenue"');
    expect(onInsertActiveAnswer.mock.calls[0]?.[0]).toContain("```mermaid");
    expect(onInsertActiveAnswer.mock.calls[0]?.[0]).toContain("flowchart TD");
    expect(onInsertActiveAnswer.mock.calls[0]?.[0]).toContain("| Quarter | Value |");
  });
});
