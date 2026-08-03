import {
  deepSpaceThreadReducer,
  initialDeepSpaceThreadState,
} from "../app/dashboard/deepspace/_lib/deepspace-thread";
import type { DeepSpaceStreamEvent } from "../app/dashboard/deepspace/_lib/deepspace-stream";
import { expect, test, describe } from "vitest";

describe("TimelineStep Model", () => {
  test("should normalize cumulative assistant deltas without duplicate words", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Explain",
    });

    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    const events: DeepSpaceStreamEvent[] = [
      { event: "delta", data: { text: "The" } },
      { event: "delta", data: { text: "The user" } },
      { event: "delta", data: { text: "The user wants" } },
    ];

    state = events.reduce(
      (s, e) => deepSpaceThreadReducer(s, { type: "stream_event", event: e }),
      state,
    );

    const message = state.messages.find((m) => m.id === assistantId);
    expect(message?.rawContent).toBe("The user wants");
    expect(message?.content).toBe("The user wants");
  });

  test("should expose live write-file diff stats before tool_result", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Edit file",
    });

    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_start",
        data: {
          step_id: "write-1",
          tool_id: "tool-write-1",
          tool_name: "write_file",
          tool_input: {
            path: "report.md",
            content: "first line\nsecond line",
          },
        },
      },
    });

    const message = state.messages.find((m) => m.id === assistantId);
    const step = message?.agentSteps?.[0];

    expect(step?.status).toBe("running");
    expect(step?.diffStats).toMatchObject({
      path: "report.md",
      additions: 2,
      deletions: 0,
    });
  });

  test("should merge agent_testing and agent_verifying into timeline", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Run tests",
    });

    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    const events: DeepSpaceStreamEvent[] = [
      {
        event: "agent_testing",
        data: {
          step_id: "test-1",
          tool_id: "call-1",
          tool_name: "bash",
          tool_input: { command: "pytest" },
          status: "running",
          phase: "testing",
        },
      },
      {
        event: "agent_verifying",
        data: {
          step_id: "test-1",
          tool_id: "call-1",
          tool_name: "bash",
          tool_input: { command: "pytest" },
          success: true,
          output: "tests passed",
          status: "completed",
          phase: "testing",
          duration_ms: 150,
        },
      },
    ];

    state = events.reduce(
      (s, e) => deepSpaceThreadReducer(s, { type: "stream_event", event: e }),
      state,
    );

    const message = state.messages.find((m) => m.id === assistantId);
    expect(message).toBeDefined();

    // Test that the timeline array is correctly populated
    expect(message!.timeline).toBeDefined();
    expect(message!.timeline!.length).toBe(1);

    const step = message!.timeline![0];
    expect(step.type).toBe("testing");
    expect(step.status).toBe("completed");
    expect(step.success).toBe(true);
    expect(step.toolOutput).toBe("tests passed");
    expect(step.durationMs).toBe(150);
  });

  test("should merge agent_self_correct gracefully", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Run tests",
    });

    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    const events: DeepSpaceStreamEvent[] = [
      {
        event: "agent_testing",
        data: {
          step_id: "test-2",
          tool_id: "call-2",
          tool_name: "bash",
          status: "running",
          phase: "testing",
        },
      },
      {
        event: "agent_self_correct",
        data: {
          step_id: "test-2",
          tool_id: "call-2",
          tool_name: "bash",
          success: false,
          output: "tests failed",
          status: "failed",
          phase: "testing",
          duration_ms: 200,
        },
      },
    ];

    state = events.reduce(
      (s, e) => deepSpaceThreadReducer(s, { type: "stream_event", event: e }),
      state,
    );

    const message = state.messages.find((m) => m.id === assistantId);
    expect(message!.timeline!.length).toBe(1);

    const step = message!.timeline![0];
    expect(step.status).toBe("failed"); // Self-correcting implies a failure state initially before next phase
    expect(step.success).toBe(false);
    expect(step.toolOutput).toBe("tests failed");
  });

  test("keeps thinking, tool activity, and the next thought in streamed order", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Create a task list",
    });

    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    const events: DeepSpaceStreamEvent[] = [
      {
        event: "thinking",
        data: { step_id: "think-1", turn_index: 1, text: "I will plan the task list." },
      },
      {
        event: "tool_delta",
        data: {
          step_id: "tool_stream_1_0",
          tool_id: "call-todo-1",
          tool_name: "todo_write",
          turn_index: 1,
          text: '{"tasks":[',
        },
      },
      {
        event: "tool_start",
        data: {
          step_id: "tool_stream_1_0",
          tool_id: "call-todo-1",
          tool_name: "todo_write",
          tool_input: { tasks: [] },
          turn_index: 1,
        },
      },
      {
        event: "tool_result",
        data: {
          step_id: "tool_stream_1_0",
          tool_id: "call-todo-1",
          tool_name: "todo_write",
          output: "10 tasks saved",
          success: true,
          turn_index: 1,
        },
      },
      {
        event: "observing",
        data: {
          step_id: "tool_stream_1_0_observe",
          tool_id: "call-todo-1",
          tool_name: "todo_write",
          summary: "Task list saved; checking completion.",
          success: true,
          turn_index: 1,
        },
      },
      {
        event: "thinking",
        data: { step_id: "think-2", turn_index: 2, text: "I can now summarize the plan." },
      },
      { event: "done", data: { step_id: "final-1", turn_index: 2 } },
    ];

    state = events.reduce(
      (current, event) => deepSpaceThreadReducer(current, { type: "stream_event", event }),
      state,
    );

    const timeline = state.messages.find((message) => message.id === assistantId)?.timeline;
    expect(timeline?.map((step) => step.type)).toEqual([
      "thinking",
      "tool_call",
      "observation",
      "thinking",
      "observation",
    ]);
    expect(timeline?.[0]).toMatchObject({ details: "I will plan the task list.", status: "completed" });
    expect(timeline?.[1]).toMatchObject({
      toolName: "todo_write",
      toolInputStream: '{"tasks":[',
      toolOutput: "10 tasks saved",
      status: "completed",
    });
    expect(timeline?.[3]).toMatchObject({
      details: "I can now summarize the plan.",
      status: "completed",
    });
  });
});
