import { describe, expect, it } from "vitest";

import { deepSpaceThreadReducer, initialDeepSpaceThreadState } from "../app/dashboard/deepspace/_lib/deepspace-thread";

describe("durable run model", () => {
  it("keeps the newest event cursor and never regresses the checkpoint", () => {
    const started = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: { event: "meta", data: { durable_run_id: "run-1", sequence: 4, checkpoint_sequence: 3, status: "running" } },
    });
    const advanced = deepSpaceThreadReducer(started, {
      type: "stream_event",
      event: { event: "meta", data: { durable_run_id: "run-1", sequence: 8, checkpoint_sequence: 2, status: "running" } },
    });
    expect(advanced.durableRun).toMatchObject({ runId: "run-1", lastSequence: 8, checkpointSequence: 3 });
  });
});
