import {
  findPendingUserQuestion,
  shouldResumePendingUserQuestion,
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
    expect(message?.thinkingContent).toBeFalsy();
    expect(message?.agentSteps).toEqual([]);
  });

  test("keeps provisional answer text out of activity when a retry replaces it", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Help me plan this",
    });
    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: { event: "delta", data: { text: "I need one more detail first." } },
    });
    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "model_message",
        data: { text: "I need one more detail first.", turn_index: 1 },
      },
    });
    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: { event: "replace", data: { content: "" } },
    });

    const message = state.messages.find((item) => item.id === assistantId);
    expect(message?.content).toBe("");
    expect(message?.thinkingContent).toBeFalsy();
    expect(message?.timeline).toEqual([
      expect.objectContaining({
        type: "model_message",
        title: "Model message",
        details: "I need one more detail first.",
      }),
    ]);
  });

  test("keeps an answer visible when a real tool begins", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Check my calendar",
    });
    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: { event: "delta", data: { text: "I will check your calendar." } },
    });
    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_start",
        data: {
          step_id: "calendar-1",
          tool_id: "calendar-1",
          tool_name: "list_events",
          tool_input: {},
        },
      },
    });

    const message = state.messages.find((item) => item.id === assistantId);
    expect(message?.content).toBe("I will check your calendar.");
    expect(message?.thinkingContent).toBeFalsy();
    expect(message?.agentSteps).toEqual([
      expect.objectContaining({ type: "tool_start", toolName: "list_events" }),
    ]);
  });

  test("keeps a real streamed media artifact on the assistant message", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Generate an image",
    });
    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "artifact",
        data: {
          artifact: {
            id: "artifact-1",
            kind: "image",
            status: "ready",
            title: "Generated image",
            content_type: "image/png",
            size_bytes: 42,
            url: "/api/v1/deepspace/artifacts/artifact-1/content",
          },
        },
      },
    });

    expect(state.messages.find((message) => message.id === assistantId)?.artifacts).toEqual([
      expect.objectContaining({ id: "artifact-1", kind: "image" }),
    ]);
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

  test("keeps only real thinking and tool activity in streamed order", () => {
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
    expect(timeline?.map((step) => step.type)).toEqual(["thinking", "tool_call", "thinking"]);
    expect(timeline?.[0]).toMatchObject({
      details: "I will plan the task list.",
      status: "completed",
    });
    expect(timeline?.[1]).toMatchObject({
      toolName: "todo_write",
      toolInputStream: '{"tasks":[',
      toolOutput: "10 tasks saved",
      status: "completed",
    });
    expect(timeline?.[2]).toMatchObject({
      details: "I can now summarize the plan.",
      status: "completed",
    });
  });

  test("keeps the composer available and resumes an ask_user question", () => {
    let state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "submit_query",
      query: "Help me choose a format",
    });
    const assistantId = state.activeAssistantId;
    if (!assistantId) throw new Error("No active assistant");

    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "tool_result",
        data: {
          tool_name: "ask_user",
          tool_id: "ask-1",
          step_id: "step-1",
          success: true,
          output: '{"awaiting_user":true}',
        },
      },
    });
    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "ask_user_question",
        data: {
          tool_name: "ask_user",
          tool_id: "ask-1",
          step_id: "step-1",
          question_id: "question-1",
          message: "Which format should I use?",
        },
      },
    });
    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "delta",
        data: { text: "Which format should I use?" },
      },
    });
    state = deepSpaceThreadReducer(state, {
      type: "stream_event",
      event: { event: "done", data: { status: "awaiting_user" } },
    });

    expect(state.isStreaming).toBe(false);
    expect(findPendingUserQuestion(state.messages)).toEqual({
      messageId: assistantId,
      questionId: "question-1",
    });
    expect(shouldResumePendingUserQuestion(state.messages, "hi")).toBe(false);
    expect(shouldResumePendingUserQuestion(state.messages, "Markdown")).toBe(true);

    state = deepSpaceThreadReducer(state, {
      type: "resume_user_question",
      messageId: assistantId,
      query: "Markdown",
    });
    expect(state.isStreaming).toBe(true);
    expect(state.messages).toHaveLength(2);
    expect(
      state.messages.some((message) => message.role === "user" && message.content === "Markdown"),
    ).toBe(false);
    expect(state.messages.find((message) => message.id === assistantId)).toMatchObject({
      status: "streaming",
      userQuestionAnswer: "Markdown",
    });
    expect(state.messages.find((message) => message.id === assistantId)?.content).toBe("");
    expect(
      state.messages
        .find((message) => message.id === assistantId)
        ?.timeline?.find((step) => step.data?.question_id === "question-1")?.status,
    ).toBe("completed");
    expect(findPendingUserQuestion(state.messages)).toBeNull();
  });

  test("rehydrates a question answer inside the original assistant turn", () => {
    const state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "load_history",
      conversationId: "conversation-1",
      messages: [
        {
          id: "assistant-question",
          role: "assistant",
          content: "Which format should I use? I need one choice before continuing.",
          created_at: "2026-08-08T10:00:00.000Z",
          metadata_json: {
            agent_steps: [
              {
                id: "question-step",
                type: "ask_user_question",
                status: "completed",
                startedAt: "2026-08-08T10:00:00.000Z",
                data: { question_id: "question-1", message: "Which format should I use?" },
              },
            ],
          },
        },
        {
          id: "user-answer",
          role: "user",
          content: "Markdown",
          created_at: "2026-08-08T10:01:00.000Z",
          metadata_json: { answer_to_question_id: "question-1" },
        },
      ],
    });

    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({
      id: "assistant-question",
      userQuestionAnswer: "Markdown",
    });
    expect(state.messages[0]?.content).toBe("I need one choice before continuing.");
  });

  test("keeps model messages emitted before a question after history reload", () => {
    const state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "load_history",
      conversationId: "conversation-1",
      messages: [
        {
          id: "assistant-question-with-context",
          role: "assistant",
          content: "Which repository should I inspect?",
          created_at: "2026-08-08T10:00:00.000Z",
          metadata_json: {
            status: "awaiting_user",
            agent_steps: [
              {
                id: "model-message-step",
                type: "model_message",
                status: "completed",
                startedAt: "2026-08-08T10:00:01.000Z",
                completedAt: "2026-08-08T10:00:02.000Z",
                data: {
                  text: "I found the connected GitHub account and will inspect its repositories.",
                  phase: "exploring",
                },
              },
              {
                id: "question-step",
                type: "ask_user_question",
                status: "awaiting_approval",
                startedAt: "2026-08-08T10:00:03.000Z",
                data: { question_id: "question-2", message: "Which repository should I inspect?" },
              },
            ],
          },
        },
      ],
    });

    expect(state.messages[0]?.timeline?.map((step) => step.type)).toEqual([
      "model_message",
      "permission",
    ]);
    expect(state.messages[0]?.timeline?.[0]).toMatchObject({
      title: "Model message",
      details: "I found the connected GitHub account and will inspect its repositories.",
    });
  });

  test("rehydrates persisted timeline events without merging thought segments", () => {
    const state = deepSpaceThreadReducer(initialDeepSpaceThreadState, {
      type: "load_history",
      conversationId: "conversation-ordered",
      messages: [
        {
          id: "assistant-ordered",
          role: "assistant",
          content: "Completed answer",
          created_at: "2026-08-09T10:00:00.000Z",
          metadata_json: {
            thinking: { content: "first thoughtsecond thought" },
            timeline_events: [
              {
                event: "thinking",
                data: { text: "first thought", timestamp: "2026-08-09T10:00:01.000Z" },
              },
              {
                event: "tool_result",
                data: {
                  tool_name: "web_search",
                  tool_id: "call-1",
                  step_id: "step-1",
                  success: true,
                  output: "search complete",
                  timestamp: "2026-08-09T10:00:02.000Z",
                },
              },
              {
                event: "thinking",
                data: { text: "second thought", timestamp: "2026-08-09T10:00:03.000Z" },
              },
            ],
          },
        },
      ],
    });

    const timeline = state.messages[0]?.timeline;
    expect(timeline?.map((step) => step.type)).toEqual(["thinking", "tool_call", "thinking"]);
    expect(timeline?.[0]?.details).toBe("first thought");
    expect(timeline?.[2]?.details).toBe("second thought");
  });
});
