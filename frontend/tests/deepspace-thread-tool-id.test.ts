import { describe, expect, it } from "vitest";

import {
  deepSpaceThreadReducer,
  initialDeepSpaceThreadState,
} from "../app/dashboard/deepspace/_lib/deepspace-thread";

describe("deepSpaceThreadReducer tool streaming", () => {
  it("keeps streamed thinking visible after completion and history reload", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: {
        event: "start",
        data: {
          message_id: "assistant-thinking",
          conversation_id: "conv-thinking",
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "thinking",
        data: { text: "First thought." },
      },
    });
    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "done",
        data: {},
      },
    });

    expect(state.messages[0]?.thinkingContent).toBe("First thought.");

    const reloaded = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "load_history",
      conversationId: "conv-thinking",
      messages: [
        {
          id: "assistant-thinking",
          role: "assistant",
          content: "Answer",
          created_at: new Date().toISOString(),
          metadata_json: { thinking: { content: "First thought." } },
        },
      ],
    });

    expect(reloaded.messages[0]?.thinkingContent).toBe("First thought.");
  });

  it("matches tool results by tool id when the same tool runs multiple times", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: {
        event: "start",
        data: {
          message_id: "assistant-1",
          conversation_id: "conv-1",
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_start",
        data: {
          step_id: "step-1",
          tool_id: "call-1",
          tool_name: "web_search",
          tool_input: { query: "alpha" },
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_start",
        data: {
          step_id: "step-1",
          tool_id: "call-2",
          tool_name: "web_search",
          tool_input: { query: "beta" },
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_result",
        data: {
          step_id: "step-1",
          tool_id: "call-1",
          tool_name: "web_search",
          tool_input: { query: "alpha" },
          output: "alpha result",
          success: true,
          duration_ms: 25,
          completed_at: new Date().toISOString(),
        },
      },
    });

    const stepsAfterFirstResult = state.messages[0]?.agentSteps ?? [];
    expect(stepsAfterFirstResult).toHaveLength(2);
    expect(stepsAfterFirstResult[0]?.tool_id).toBe("call-1");
    expect(stepsAfterFirstResult[0]?.status).toBe("completed");
    expect(stepsAfterFirstResult[0]?.toolOutput).toBe("alpha result");
    expect(stepsAfterFirstResult[1]?.tool_id).toBe("call-2");
    expect(stepsAfterFirstResult[1]?.status).toBe("running");

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_result",
        data: {
          step_id: "step-1",
          tool_id: "call-2",
          tool_name: "web_search",
          tool_input: { query: "beta" },
          output: "beta result",
          success: true,
          duration_ms: 30,
          completed_at: new Date().toISOString(),
        },
      },
    });

    const finalSteps = state.messages[0]?.agentSteps ?? [];
    expect(finalSteps[1]?.tool_id).toBe("call-2");
    expect(finalSteps[1]?.status).toBe("completed");
    expect(finalSteps[1]?.toolOutput).toBe("beta result");
  });

  it("appends tool_delta output to the running tool pane", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: {
        event: "start",
        data: {
          message_id: "assistant-1",
          conversation_id: "conv-1",
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_start",
        data: {
          step_id: "step-2",
          tool_id: "bash-1",
          tool_name: "bash",
          tool_input: { command: "echo hi" },
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_delta",
        data: {
          step_id: "step-2",
          tool_id: "bash-1",
          tool_name: "bash",
          tool_input: { command: "echo hi" },
          text: "hi\n",
        },
      },
    });

    const steps = state.messages[0]?.agentSteps ?? [];
    expect(steps[0]?.status).toBe("running");
    expect(steps[0]?.toolOutput).toBe("hi\n");
  });

  it("preserves streamed tool output when the final tool_result arrives", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: {
        event: "start",
        data: {
          message_id: "assistant-1",
          conversation_id: "conv-1",
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_start",
        data: {
          step_id: "step-3",
          tool_id: "sync-1",
          tool_name: "sync_connector",
          tool_input: { integration_slug: "github" },
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_delta",
        data: {
          step_id: "step-3",
          tool_id: "sync-1",
          tool_name: "sync_connector",
          tool_input: { integration_slug: "github" },
          stream: "system",
          text: "Fetching source data from github.\n",
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_result",
        data: {
          step_id: "step-3",
          tool_id: "sync-1",
          tool_name: "sync_connector",
          tool_input: { integration_slug: "github" },
          output: "Sync completed.",
          success: true,
          duration_ms: 125,
          completed_at: new Date().toISOString(),
        },
      },
    });

    const steps = state.messages[0]?.agentSteps ?? [];
    expect(steps[0]?.status).toBe("completed");
    expect(steps[0]?.toolOutput).toContain("[system] Fetching source data from github.");
    expect(steps[0]?.toolOutput).toContain("Sync completed.");
  });

  it("merges agent lifecycle phases into a single tool step card", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: {
        event: "start",
        data: {
          message_id: "assistant-3",
          conversation_id: "conv-3",
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_start",
        data: {
          step_id: "step-4",
          tool_id: "call-4",
          tool_name: "bash",
          tool_input: { command: "echo hi" },
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_result",
        data: {
          step_id: "step-4",
          tool_id: "call-4",
          tool_name: "bash",
          tool_input: { command: "echo hi" },
          output: "hello\n",
          success: true,
          duration_ms: 20,
          completed_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "agent_testing",
        data: {
          step_id: "step-4",
          tool_id: "call-4",
          tool_name: "bash",
          output: "Background tests passed.",
          success: true,
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
        },
      },
    });

    const testingSteps = state.messages[0]?.agentSteps ?? [];
    expect(testingSteps).toHaveLength(1);
    expect(testingSteps[0]?.type).toBe("agent_testing");
    expect(testingSteps[0]?.tool_id).toBe("call-4");
    expect(testingSteps[0]?.status).toBe("completed");
    expect(testingSteps[0]?.toolOutput).toContain("hello\n");
    expect(testingSteps[0]?.toolOutput).toContain("Background tests passed.");

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "agent_verifying",
        data: {
          step_id: "step-4",
          tool_id: "call-4",
          tool_name: "bash",
          output: "Verification confirmed.",
          success: true,
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
        },
      },
    });

    const verifyingSteps = state.messages[0]?.agentSteps ?? [];
    expect(verifyingSteps).toHaveLength(1);
    expect(verifyingSteps[0]?.type).toBe("agent_verifying");
    expect(verifyingSteps[0]?.status).toBe("completed");
    expect(verifyingSteps[0]?.toolOutput).toContain("Background tests passed.");
    expect(verifyingSteps[0]?.toolOutput).toContain("Verification confirmed.");

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "agent_self_correct",
        data: {
          step_id: "step-4",
          tool_id: "call-4",
          tool_name: "bash",
          output: "Self-correction triggered.",
          success: false,
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
        },
      },
    });

    const selfCorrectSteps = state.messages[0]?.agentSteps ?? [];
    expect(selfCorrectSteps).toHaveLength(1);
    expect(selfCorrectSteps[0]?.type).toBe("agent_self_correct");
    expect(selfCorrectSteps[0]?.status).toBe("failed");
    expect(selfCorrectSteps[0]?.toolOutput).toContain("Self-correction triggered.");
  });

  it("merges approval, execution, and observation lifecycle events into one card", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "stream_event",
      event: {
        event: "start",
        data: {
          message_id: "assistant-merge",
          conversation_id: "conv-merge",
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "permission_request",
        data: {
          step_id: "step-merge",
          tool_id: "call-merge",
          tool_name: "web_search",
          tool_input: { query: "alpha" },
          permission_level: "approval",
          tier: 2,
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_start",
        data: {
          step_id: "step-merge",
          tool_id: "call-merge",
          tool_name: "web_search",
          tool_input: { query: "alpha" },
          permission_level: "approved",
          started_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_delta",
        data: {
          step_id: "step-merge",
          tool_id: "call-merge",
          tool_name: "web_search",
          tool_input: { query: "alpha" },
          stream: "stdout",
          text: "searching\n",
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_result",
        data: {
          step_id: "step-merge",
          tool_id: "call-merge",
          tool_name: "web_search",
          tool_input: { query: "alpha" },
          output: "alpha result",
          success: true,
          duration_ms: 31,
          completed_at: new Date().toISOString(),
        },
      },
    });

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "observing",
        data: {
          step_id: "step-merge",
          tool_id: "call-merge",
          tool_name: "web_search",
          tool_input: { query: "alpha" },
          summary: "Observation confirmed.",
          success: true,
          observed_at: new Date().toISOString(),
        },
      },
    });

    const steps = state.messages[0]?.agentSteps ?? [];
    expect(steps).toHaveLength(1);
    expect(steps[0]?.status).toBe("completed");
    expect(steps[0]?.type).toBe("tool_result");
    expect(steps[0]?.toolOutput).toContain("searching");
    expect(steps[0]?.toolOutput).toContain("alpha result");
    expect(steps[0]?.toolOutput).toContain("[system] Observation confirmed.");
  });

  it("compacts merged lifecycle events from history loading", () => {
    const state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "load_history",
      conversationId: "conv-history",
      messages: [
        {
          id: "assistant-history",
          role: "assistant",
          content: "done",
          created_at: new Date().toISOString(),
          metadata_json: {
            agent_steps: [
              {
                id: "history-step-1",
                type: "permission_request",
                status: "awaiting_approval",
                step_id: "history-step",
                tool_id: "history-tool",
                toolName: "web_search",
                toolInput: { query: "history" },
                permissionLevel: "approval",
                startedAt: new Date().toISOString(),
                data: {
                  step_id: "history-step",
                  tool_id: "history-tool",
                  tool_name: "web_search",
                  tool_input: { query: "history" },
                },
              },
              {
                id: "history-step-2",
                type: "tool_start",
                status: "running",
                step_id: "history-step",
                tool_id: "history-tool",
                toolName: "web_search",
                toolInput: { query: "history" },
                permissionLevel: "approved",
                startedAt: new Date().toISOString(),
                data: {
                  step_id: "history-step",
                  tool_id: "history-tool",
                  tool_name: "web_search",
                  tool_input: { query: "history" },
                },
              },
              {
                id: "history-step-3",
                type: "tool_result",
                status: "completed",
                step_id: "history-step",
                tool_id: "history-tool",
                toolName: "web_search",
                toolInput: { query: "history" },
                toolOutput: "history result",
                success: true,
                startedAt: new Date().toISOString(),
                completedAt: new Date().toISOString(),
                data: {
                  step_id: "history-step",
                  tool_id: "history-tool",
                  tool_name: "web_search",
                  tool_input: { query: "history" },
                  output: "history result",
                },
              },
              {
                id: "history-step-4",
                type: "observing",
                status: "completed",
                step_id: "history-step",
                tool_id: "history-tool",
                toolName: "web_search",
                toolInput: { query: "history" },
                toolOutput: "Confirmed from history.",
                success: true,
                startedAt: new Date().toISOString(),
                completedAt: new Date().toISOString(),
                data: {
                  step_id: "history-step",
                  tool_id: "history-tool",
                  tool_name: "web_search",
                  tool_input: { query: "history" },
                  summary: "Confirmed from history.",
                },
              },
            ],
          },
        },
      ],
    });

    const steps = state.messages[0]?.agentSteps ?? [];
    expect(steps).toHaveLength(1);
    expect(steps[0]?.type).toBe("tool_result");
    expect(steps[0]?.status).toBe("completed");
    expect(steps[0]?.toolOutput).toContain("history result");
    expect(steps[0]?.toolOutput).toContain("[system] Confirmed from history.");
  });
});
