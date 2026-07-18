import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OrchestrationCanvas from "../app/dashboard/deepspace/_components/OrchestrationCanvas";
import type { MissionCanvasState } from "../app/dashboard/deepspace/_lib/deepspace-stream";

describe("durable approval queue", () => {
  it("renders persisted risk evidence as a visible approval item", () => {
    const mission: MissionCanvasState = {
      missionId: "approval-1",
      objective: "Approve a connector write.",
      status: "awaiting_approval",
      phase: "awaiting_approval",
      startedAt: new Date().toISOString(),
      lastUpdatedAt: new Date().toISOString(),
      approvalQueue: [{ lane_id: "connector", lane_type: "connector", message: "External side effect requires approval." }],
      lanes: [],
      globalEvents: [],
    };
    render(<OrchestrationCanvas mission={mission} />);
    expect(screen.getByText("Approval Queue")).toBeInTheDocument();
    expect(screen.getByText(/External side effect requires approval/i)).toBeInTheDocument();
  });
});
