import { describe, expect, it } from "vitest";

import {
  deepSpaceThreadReducer,
  initialDeepSpaceThreadState,
} from "../app/dashboard/deepspace/_lib/deepspace-thread";

describe("DeepSpace durable thread state", () => {
  it("hydrates cursor, checkpoint, budget, recovery, and supervisor state from events", () => {
    const state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: {
        event: "meta",
        data: {
          durable_run_id: "run-42",
          durable_event_type: "run_started",
          sequence: 3,
          checkpoint_sequence: 2,
          continuation_epoch: 1,
          recovery_count: 0,
          status: "running",
          budget_usage: { tokens: 12, cost: 0.01 },
          budget_limits: { tokens: 100, cost: 1 },
          supervisor_decision: "continue",
        },
      },
    });

    expect(state.durableRun).toMatchObject({
      runId: "run-42",
      status: "running",
      lastSequence: 3,
      checkpointSequence: 2,
      continuationEpoch: 1,
      recoveryCount: 0,
      reconnectState: "connected",
      budgetUsage: { tokens: 12, cost: 0.01 },
      budgetLimits: { tokens: 100, cost: 1 },
      supervisorDecision: "continue",
      replayReadOnly: true,
    });
  });

  it("advances the cursor without regressing the durable checkpoint", () => {
    const started = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: {
        event: "meta",
        data: {
          durable_run_id: "run-42",
          durable_event_type: "run_started",
          sequence: 3,
          checkpoint_sequence: 2,
          status: "running",
        },
      },
    });
    const resumed = deepSpaceThreadReducer(started, {
      type: "stream_event",
      event: {
        event: "meta",
        data: {
          durable_run_id: "run-42",
          durable_event_type: "run_resumed",
          sequence: 8,
          status: "running",
          recovery_count: 1,
        },
      },
    });

    expect(resumed.durableRun).toMatchObject({
      runId: "run-42",
      lastSequence: 8,
      checkpointSequence: 2,
      recoveryCount: 1,
      reconnectState: "connected",
    });
  });
});
