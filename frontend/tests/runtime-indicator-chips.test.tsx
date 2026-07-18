import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RuntimeIndicatorChips from "../app/dashboard/deepspace/_components/RuntimeIndicatorChips";

describe("RuntimeIndicatorChips", () => {
  it("renders planner, subagent, hook, and workspace runtime posture", () => {
    render(
      <RuntimeIndicatorChips
        indicators={{
          executionMode: "auto_review",
          plannerMode: "structured",
          subagentProfile: "research",
          runtimeHooksEnabled: false,
          workspaceModeEnabled: true,
        }}
      />,
    );

    expect(screen.getByText(/mode: auto review/i)).toBeInTheDocument();
    expect(screen.getByText(/planner: structured/i)).toBeInTheDocument();
    expect(screen.getByText(/subagent: research/i)).toBeInTheDocument();
    expect(screen.getByText(/hooks paused/i)).toBeInTheDocument();
    expect(screen.getByText(/code mode scoped/i)).toBeInTheDocument();
  });
});
