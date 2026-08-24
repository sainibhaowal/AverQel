import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DeepSpaceThinkingPanel from "../app/dashboard/deepspace/_components/DeepSpaceThinkingPanel";

describe("DeepSpace verified task progress", () => {
  it("keeps persisted model thinking visible when tool steps are restored", () => {
    render(
      <DeepSpaceThinkingPanel
        content="I checked the sources and will summarize the verified findings."
        isStreaming={false}
        timeline={[
          {
            id: "search-result",
            stepId: "search-result",
            turnIndex: 1,
            phase: "exploring",
            type: "tool_call",
            title: "Searching the web",
            status: "completed",
            startedAt: "2026-08-09T00:00:00Z",
            completedAt: "2026-08-09T00:00:01Z",
            toolName: "web_search",
            toolId: "call-1",
          },
        ]}
      />,
    );

    expect(screen.getByTestId("deepspace-thinking-stream")).toHaveTextContent(
      "I checked the sources",
    );
    expect(screen.getByText("Searching the web")).toBeInTheDocument();
  });

  it("derives progress only from a real todo tool result", () => {
    render(
      <DeepSpaceThinkingPanel
        content=""
        isStreaming={false}
        timeline={[
          {
            id: "todo-result",
            stepId: "todo-result",
            turnIndex: 1,
            phase: "verifying",
            type: "tool_call",
            title: "Check Task Ledger",
            status: "completed",
            startedAt: new Date().toISOString(),
            completedAt: new Date().toISOString(),
            toolName: "todo_check",
            toolId: "call-1",
            toolOutput: JSON.stringify({
              completed_count: 1,
              tasks: [
                { id: "task-1", content: "Research sources", status: "completed" },
                { id: "task-2", content: "Write the report", status: "in_progress" },
              ],
            }),
          },
        ]}
      />,
    );

    expect(screen.getByTestId("deepspace-task-progress")).toHaveTextContent("1/2 complete");
    expect(screen.getByTestId("deepspace-task-progress")).toHaveTextContent("Research sources");
    expect(screen.getByTestId("deepspace-task-progress")).toHaveTextContent("Write the report");
  });

  it("collapses completed timeline entries while keeping the live entry open", () => {
    const { rerender } = render(
      <DeepSpaceThinkingPanel
        content=""
        isStreaming
        timeline={[
          {
            id: "finished-step",
            stepId: "finished-step",
            turnIndex: 1,
            phase: "exploring",
            type: "thinking",
            title: "Completed thought",
            details: "The completed details remain available when expanded.",
            status: "completed",
            startedAt: "2026-08-09T00:00:00Z",
            completedAt: "2026-08-09T00:00:01Z",
          },
          {
            id: "live-step",
            stepId: "live-step",
            turnIndex: 1,
            phase: "testing",
            type: "tool_call",
            title: "Live tool call",
            status: "running",
            startedAt: "2026-08-09T00:00:02Z",
            toolName: "web_search",
          },
        ]}
      />,
    );

    const completedBanner = screen.getByRole("button", { name: /Completed thought/i });
    const liveBanner = screen.getByRole("button", { name: /Live tool call/i });
    expect(completedBanner).toHaveAttribute("aria-expanded", "false");
    expect(liveBanner).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(completedBanner);
    expect(completedBanner).toHaveAttribute("aria-expanded", "true");

    rerender(
      <DeepSpaceThinkingPanel
        content=""
        isStreaming={false}
        timeline={[
          {
            id: "finished-step",
            stepId: "finished-step",
            turnIndex: 1,
            phase: "exploring",
            type: "thinking",
            title: "Completed thought",
            details: "The completed details remain available when expanded.",
            status: "completed",
            startedAt: "2026-08-09T00:00:00Z",
            completedAt: "2026-08-09T00:00:01Z",
          },
          {
            id: "live-step",
            stepId: "live-step",
            turnIndex: 1,
            phase: "testing",
            type: "tool_call",
            title: "Live tool call",
            status: "completed",
            startedAt: "2026-08-09T00:00:02Z",
            completedAt: "2026-08-09T00:00:03Z",
            toolName: "web_search",
          },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: /Completed thought/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("button", { name: /Live tool call/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });
});
