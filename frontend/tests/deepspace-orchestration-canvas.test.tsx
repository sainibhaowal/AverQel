import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OrchestrationCanvas from "../app/dashboard/deepspace/_components/OrchestrationCanvas";
import type { MissionCanvasState } from "../app/dashboard/deepspace/_lib/deepspace-stream";

describe("OrchestrationCanvas", () => {
  it("renders mission overview, dependency map, and lane activity", () => {
    const mission: MissionCanvasState = {
      missionId: "mission-42",
      objective: "Research the connector outage and draft an operator update.",
      status: "running",
      phase: "executing",
      executionMode: "auto_review",
      plannerSource: "model",
      summary: "Research lane is gathering evidence while writer lane prepares the memo.",
      startedAt: new Date().toISOString(),
      lastUpdatedAt: new Date().toISOString(),
      runtimeState: {
        plannerMode: "structured",
        plannerValidationStatus: "validated",
        runtimeHooksState: "active",
        subagentProfile: "analysis",
        subagentProfileClassification: "preferred_profile",
        workspaceModeEnabled: true,
        diagnostics: {
          planner: {
            laneCount: 2,
            parallelLimit: 2,
          },
          policy: {
            counts: {
              allow: 3,
              approval: 1,
              block: 0,
            },
            recent: [
              {
                toolName: "edit_file",
                decision: "approval",
                reason: "Human approval required before editing the template.",
              },
            ],
          },
          hooks: {
            recent: [
              {
                phase: "pre_tool",
                hook: "tenant_guard",
                status: "applied",
                changedFields: ["tool_input"],
              },
            ],
          },
          compaction: {
            recent: [
              {
                saved_tokens: 900,
              },
            ],
          },
          toolDensity: {
            started: 4,
            completed: 3,
            failed: 0,
            blocked: 0,
            awaitingApproval: 1,
          },
        },
      },
      signals: {
        research: true,
        writer: true,
      },
      approvalQueue: [
        {
          lane_id: "writer_lane",
          lane_type: "writer",
          message: "Approval needed before updating the customer template.",
        },
      ],
      graph: {
        nodes: [{ id: "main_chat" }, { id: "writer_lane" }],
        edges: [{ from: "main_chat", to: "writer_lane" }],
      },
      globalEvents: [
        {
          id: "mission-start",
          kind: "mission_start",
          message: "Mission started.",
          at: new Date().toISOString(),
        },
      ],
      lanes: [
        {
          laneId: "main_chat",
          laneType: "main_chat",
          title: "Main Chat",
          prompt: "Coordinate the mission.",
          priority: 100,
          status: "running",
          dependsOn: [],
          blockedBy: [],
          subagentType: null,
          events: [],
        },
        {
          laneId: "writer_lane",
          laneType: "writer",
          title: "Writer Lane",
          prompt: "Draft the operator update.",
          priority: 80,
          status: "awaiting_approval",
          dependsOn: ["main_chat"],
          blockedBy: [],
          subagentType: "writer",
          metadata: {
            requested_subagent_type: "general-purpose",
            resolved_subagent_type: "writer",
            delegation_rationale: "Draft the operator-facing memo after research is complete.",
            tool_density: {
              started: 2,
              completed: 2,
            },
            lane_lifecycle_summary: {
              status: "awaiting_approval",
              elapsed_ms: 4200,
            },
          },
          summary: "Draft prepared and waiting on approval.",
          events: [
            {
              id: "writer-approval",
              kind: "approval_request",
              message: "Approval needed before updating the customer template.",
              at: new Date().toISOString(),
              status: "awaiting_approval",
            },
          ],
        },
      ],
    };

    render(<OrchestrationCanvas mission={mission} />);

    expect(screen.getByText("Mission Canvas")).toBeInTheDocument();
    expect(screen.getByText(/Research the connector outage/i)).toBeInTheDocument();
    expect(screen.getByText("Dependency Map")).toBeInTheDocument();
    expect(screen.queryByText("Support + Proactive")).not.toBeInTheDocument();
    expect(screen.getByText("Mission Control")).toBeInTheDocument();
    expect(screen.getByText("Delivery + Execution")).toBeInTheDocument();
    expect(screen.getByText("Approval Queue")).toBeInTheDocument();
    expect(screen.getAllByText(/writer lane/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/validation: validated/i)).toBeInTheDocument();
    expect(screen.getByText(/hooks: active/i)).toBeInTheDocument();
    expect(screen.getByText(/delegation: preferred profile/i)).toBeInTheDocument();
    expect(screen.getByText(/profile general-purpose -> writer/i)).toBeInTheDocument();
    expect(screen.getByText("Operator Diagnostics")).toBeInTheDocument();
    expect(
      screen.getByText(/Human approval required before editing the template/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Delegation rationale/i)).toBeInTheDocument();
    expect(screen.getByText(/tools 2\/2/i)).toBeInTheDocument();
    expect(
      screen.getAllByText(/Approval needed before updating the customer template/i).length,
    ).toBeGreaterThan(0);
  });

  it("shows runtime posture badges when runtime indicators are provided", () => {
    const mission: MissionCanvasState = {
      missionId: "mission-99",
      objective: "Validate runtime visibility.",
      status: "running",
      phase: "executing",
      executionMode: "full_access",
      plannerSource: "structured",
      startedAt: new Date().toISOString(),
      lastUpdatedAt: new Date().toISOString(),
      runtimeState: {
        plannerMode: "structured",
        plannerValidationStatus: "validated",
        runtimeHooksState: "active",
        subagentProfile: "analysis",
        subagentProfileClassification: "preferred_profile",
        workspaceModeEnabled: true,
      },
      approvalQueue: [],
      lanes: [],
      globalEvents: [],
    };

    render(
      <OrchestrationCanvas
        mission={mission}
        runtimeIndicators={{
          executionMode: "full_access",
          plannerMode: "structured",
          subagentProfile: "analysis",
          runtimeHooksEnabled: true,
          workspaceModeEnabled: true,
        }}
      />,
    );

    expect(screen.getAllByText(/planner: structured/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/subagent: analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/hooks active/i)).toBeInTheDocument();
    expect(screen.getByText(/code mode scoped/i)).toBeInTheDocument();
    expect(screen.getByText(/validation: validated/i)).toBeInTheDocument();
  });

  it("shows native durable cursor, recovery, budget, and replay state", () => {
    const mission: MissionCanvasState = {
      missionId: "mission-durable",
      objective: "Resume a durable mission after a worker interruption.",
      status: "awaiting_approval",
      phase: "awaiting_approval",
      executionMode: "auto_review",
      plannerSource: "structured",
      startedAt: new Date().toISOString(),
      lastUpdatedAt: new Date().toISOString(),
      durableRuntime: {
        runId: "run-7",
        status: "awaiting_approval",
        lastSequence: 7,
        checkpointSequence: 6,
        continuationEpoch: 2,
        recoveryCount: 1,
        pendingApprovals: 1,
        reconnectState: "connected",
        budgetUsage: { tokens: 4 },
        budgetLimits: { tokens: 10 },
        supervisorDecision: "ask_human",
        replayReadOnly: true,
      },
      approvalQueue: [],
      lanes: [],
      globalEvents: [],
    };

    render(<OrchestrationCanvas mission={mission} />);

    expect(screen.getByText("Native Durable Runtime")).toBeInTheDocument();
    expect(screen.getByText("run-7")).toBeInTheDocument();
    expect(screen.getByText("#7")).toBeInTheDocument();
    expect(screen.getByText(/Replay: read-only/i)).toBeInTheDocument();
    expect(screen.getByText(/Supervisor: ask_human/i)).toBeInTheDocument();
  });
});
