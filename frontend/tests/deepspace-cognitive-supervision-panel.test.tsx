import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OrchestrationCanvas from "../app/dashboard/deepspace/_components/OrchestrationCanvas";
import type { MissionCanvasState } from "../app/dashboard/deepspace/_lib/deepspace-stream";

const mission: MissionCanvasState = {
  missionId: "cognitive-1",
  objective: "Verify cognitive supervision evidence.",
  status: "running",
  phase: "executing",
  startedAt: new Date().toISOString(),
  lastUpdatedAt: new Date().toISOString(),
  runtimeState: {
    diagnostics: { planner: { laneCount: 1, parallelLimit: 1 } },
  },
  durableRuntime: {
    runId: "run-cognitive",
    status: "running",
    lastSequence: 12,
    checkpointSequence: 11,
    continuationEpoch: 1,
    recoveryCount: 0,
    reconnectState: "connected",
    supervisorDecision: "continue",
    replayReadOnly: true,
  },
  approvalQueue: [],
  lanes: [],
  globalEvents: [],
};

describe("cognitive supervision panel", () => {
  it("shows the supervisor decision and replay posture", () => {
    render(<OrchestrationCanvas mission={mission} />);
    expect(screen.getByText(/Supervisor: continue/i)).toBeInTheDocument();
    expect(screen.getByText(/Replay: read-only/i)).toBeInTheDocument();
  });
});
