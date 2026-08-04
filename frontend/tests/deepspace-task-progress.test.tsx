import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DeepSpaceThinkingPanel from "../app/dashboard/deepspace/_components/DeepSpaceThinkingPanel";

describe("DeepSpace verified task progress", () => {
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
