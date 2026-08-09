import { render, screen } from "@testing-library/react";
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
});
