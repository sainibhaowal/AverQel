import { describe, expect, it } from "vitest";

import {
  deepSpaceThreadReducer,
  initialDeepSpaceThreadState,
} from "../app/dashboard/deepspace/_lib/deepspace-thread";
import type { DeepSpaceStreamEvent } from "../app/dashboard/deepspace/_lib/deepspace-stream";

describe("DeepSpace orchestration canvas model", () => {
  it("builds mission and lane state from orchestration stream events", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Research and draft a connector rollout plan.",
    });

    const events: DeepSpaceStreamEvent[] = [
      {
        event: "mission_start",
        data: {
          mission_id: "mission-1",
          objective: "Research and draft a connector rollout plan.",
          execution_mode: "auto_review",
          planner_source: "pending",
          runtime_state: {
            planner_mode: "structured",
          },
        },
      },
      {
        event: "mission_plan",
        data: {
          mission_id: "mission-1",
          planner_source: "model",
          runtime_state: {
            planner_validation_status: "validated",
            diagnostics: {
              planner: {
                lane_count: 2,
                parallel_limit: 2,
              },
            },
          },
          plan: {
            summary: "Two-lane mission plan.",
            signals: { research: true, writer: true },
            approval_queue: [],
            graph: {
              nodes: [{ id: "main_chat" }, { id: "writer_final" }],
              edges: [{ from: "main_chat", to: "writer_final" }],
            },
            lanes: [
              {
                lane_id: "main_chat",
                lane_type: "main_chat",
                title: "Main Chat",
                prompt: "Coordinate the mission.",
                priority: 100,
                depends_on: [],
                blocked_by: [],
                subagent_type: null,
                metadata: { role: "primary" },
                status: "planned",
              },
              {
                lane_id: "writer_final",
                lane_type: "writer",
                title: "Writer Lane",
                prompt: "Draft the rollout memo.",
                priority: 80,
                depends_on: ["main_chat"],
                blocked_by: [],
                subagent_type: "writer",
                metadata: { role: "writer" },
                status: "planned",
              },
            ],
          },
        },
      },
      {
        event: "lane_start",
        data: {
          mission_id: "mission-1",
          lane_id: "writer_final",
          lane_type: "writer",
          title: "Writer Lane",
          prompt: "Draft the rollout memo.",
          metadata: {
            delegation_rationale: "Turn the research findings into a final memo.",
          },
        },
      },
      {
        event: "lane_step_summary",
        data: {
          mission_id: "mission-1",
          lane_id: "writer_final",
          lane_type: "writer",
          message: "Drafting the rollout structure.",
        },
      },
      {
        event: "approval_request",
        data: {
          mission_id: "mission-1",
          lane_id: "writer_final",
          lane_type: "writer",
          message: "Approval needed before editing the final template.",
        },
      },
      {
        event: "lane_result",
        data: {
          mission_id: "mission-1",
          lane_id: "writer_final",
          lane_type: "writer",
          status: "completed",
          summary: "Writer lane finished cleanly.",
          output: "Final draft complete.",
          metadata: {
            tool_density: {
              started: 2,
              completed: 2,
            },
          },
        },
      },
      {
        event: "mission_done",
        data: {
          mission_id: "mission-1",
          status: "completed",
          summary: "Mission finished successfully.",
        },
      },
    ];

    state = events.reduce(
      (currentState, event) =>
        deepSpaceThreadReducer(currentState, { type: "stream_event", event }),
      state,
    );

    const assistant = state.messages.find((message) => message.role === "assistant");
    expect(assistant?.mission).toBeDefined();
    expect(assistant?.mission?.missionId).toBe("mission-1");
    expect(assistant?.mission?.plannerSource).toBe("model");
    expect(assistant?.mission?.status).toBe("completed");
    expect(assistant?.mission?.phase).toBe("completed");
    expect(assistant?.mission?.lanes).toHaveLength(2);
    expect(assistant?.mission?.runtimeState?.diagnostics?.planner?.laneCount).toBe(2);

    const writerLane = assistant?.mission?.lanes.find((lane) => lane.laneId === "writer_final");
    expect(writerLane?.status).toBe("completed");
    expect(writerLane?.summary).toBe("Writer lane finished cleanly.");
    expect(writerLane?.metadata?.delegation_rationale).toBe(
      "Turn the research findings into a final memo.",
    );
    expect(writerLane?.events.some((event) => event.kind === "approval_request")).toBe(true);
    expect(writerLane?.events.some((event) => event.kind === "lane_result")).toBe(true);
  });
});
