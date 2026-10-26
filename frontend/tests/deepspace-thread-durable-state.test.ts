import { describe, expect, it } from "vitest";

import {
  deepSpaceThreadReducer,
  initialDeepSpaceThreadState,
} from "../app/dashboard/deepspace/_lib/deepspace-thread";

describe("DeepSpace durable thread state", () => {
  it("prepends older history without losing current messages or duplicating rows", () => {
    const currentPage = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "load_history",
      conversationId: "conversation-pages",
      messages: [
        {
          id: "user-z",
          role: "user",
          content: "Second prompt",
          created_at: "2026-01-02T00:00:00.000Z",
          metadata_json: {},
        },
        {
          id: "assistant-a",
          role: "assistant",
          content: "Current answer",
          created_at: "2026-01-02T00:00:00.000Z",
          metadata_json: {},
        },
      ],
    });

    const state = deepSpaceThreadReducer(currentPage, {
      type: "prepend_history",
      conversationId: "conversation-pages",
      messages: [
        {
          id: "user-a",
          role: "user",
          content: "First prompt",
          created_at: "2026-01-02T00:00:00.000Z",
          metadata_json: {},
        },
        {
          id: "user-z",
          role: "user",
          content: "Stale duplicate",
          created_at: "2026-01-02T00:00:00.000Z",
          metadata_json: {},
        },
      ],
    });

    expect(state.messages.map((message) => message.id)).toEqual([
      "user-a",
      "user-z",
      "assistant-a",
    ]);
    expect(state.messages[1]?.content).toBe("Second prompt");
    expect(state.messages[2]?.content).toBe("Current answer");
  });

  it("restores a useful stale-worker error message from saved history", () => {
    const state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "load_history",
      conversationId: "conversation-expired-run",
      messages: [
        {
          id: "assistant-expired-run",
          role: "assistant",
          content: "Partial answer before the worker stopped.",
          created_at: "2026-10-11T12:00:00.000Z",
          metadata_json: {
            status: "error",
            error_code: "DEEPSPACE_WORKER_LEASE_EXPIRED",
            error_message: "The saved prompt is available to retry.",
          },
        },
      ],
    });

    expect(state.messages[0]?.error).toEqual({
      code: "DEEPSPACE_WORKER_LEASE_EXPIRED",
      message: "The saved prompt is available to retry.",
    });
    expect(state.messages[0]?.content).toBe("Partial answer before the worker stopped.");
  });

  it("restores measured response speed and first-token timing from history metadata", () => {
    const state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "load_history",
      conversationId: "conversation-metrics",
      messages: [
        {
          id: "assistant-metrics",
          role: "assistant",
          content: "Measured answer.",
          created_at: "2026-10-11T12:00:00.000Z",
          metadata_json: {
            status: "ready",
            provider_type: "openai-compatible",
            model_name: "metrics-model",
            provider_output_tokens: 24,
            provider_generation_duration_ms: 800,
            tokens_per_second: 30,
            tokens_per_second_unavailable_reason: null,
            time_to_first_token_ms: 420,
            provider_time_to_first_output_ms: 180,
            request_latency_ms: 1400,
            provider_usage: {
              input_tokens: 31,
              output_tokens: 24,
              usage_source: "provider",
            },
          },
        },
      ],
    });

    expect(state.messages[0]?.metrics).toMatchObject({
      providerOutputTokens: 24,
      providerGenerationDurationMs: 800,
      tokensPerSecond: 30,
      tokensPerSecondUnavailableReason: null,
      timeToFirstTokenMs: 420,
      providerTimeToFirstOutputMs: 180,
      requestLatencyMs: 1400,
      providerUsage: {
        input_tokens: 31,
        output_tokens: 24,
        usage_source: "provider",
      },
    });
  });

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
