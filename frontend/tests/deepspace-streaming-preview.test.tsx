import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const markdownRendererMock = vi.fn(({ content }: { content: string }) => (
  <div>Markdown: {content}</div>
));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceMarkdownRenderer", () => ({
  default: (props: { content: string }) => markdownRendererMock(props),
}));

import DeepSpaceThread from "../app/dashboard/deepspace/_components/DeepSpaceThread";

describe("DeepSpaceThread streaming preview", () => {
  it("shows a rich preview while streaming by mounting the markdown renderer", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_streaming_1",
            role: "assistant",
            content: "Streaming answer text",
            rawContent: "Streaming answer text",
            createdAt: new Date().toISOString(),
            status: "streaming",
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText("Markdown: Streaming answer text")).toBeInTheDocument();
    expect(markdownRendererMock).toHaveBeenCalledTimes(1);
  });

  it("renders the rich markdown view once the message is complete", () => {
    markdownRendererMock.mockClear();

    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_ready_1",
            role: "assistant",
            content: "Finished answer text",
            rawContent: "Finished answer text",
            createdAt: new Date().toISOString(),
            status: "ready",
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText("Markdown: Finished answer text")).toBeInTheDocument();
    expect(markdownRendererMock).toHaveBeenCalledTimes(1);
  });

  it("shows tool activity in the same thinking panel even without model-thinking text", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_tool_activity_1",
            role: "assistant",
            content: "",
            rawContent: "",
            createdAt: new Date().toISOString(),
            status: "streaming",
            agentSteps: [
              {
                id: "tool_step_1",
                type: "tool_result",
                toolName: "mcp_gmail_search_threads",
                toolInput: { query: "in:inbox" },
                toolOutput: "Found 13 threads",
                status: "completed",
                success: true,
                startedAt: new Date().toISOString(),
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText("Thinking & activity…")).toBeInTheDocument();
    expect(screen.getByText("mcp_gmail_search_threads")).toBeInTheDocument();
    expect(screen.getByText("Found 13 threads")).toBeInTheDocument();
  });

  it("does not render legacy aggregate thinking above a rehydrated timeline", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_rehydrated_timeline_1",
            role: "assistant",
            content: "The weather result is ready.",
            rawContent: "The weather result is ready.",
            thinkingContent: "Old aggregate thought that must not appear above the timeline.",
            createdAt: new Date().toISOString(),
            status: "ready",
            timeline: [
              {
                id: "timeline_tool_1",
                stepId: "timeline_tool_1",
                turnIndex: 0,
                phase: "exploring",
                type: "tool_output",
                title: "Weather search",
                status: "completed",
                startedAt: new Date().toISOString(),
                completedAt: new Date().toISOString(),
                toolName: "web_search",
                toolOutput: "Weather result received.",
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(
      screen.queryByText("Old aggregate thought that must not appear above the timeline."),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Weather search")).toBeInTheDocument();
  });

  it("renders tool payloads as readable labels instead of raw JSON", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_readable_tool_1",
            role: "assistant",
            content: "",
            rawContent: "",
            createdAt: new Date().toISOString(),
            status: "ready",
            agentSteps: [
              {
                id: "tool_readable_1",
                type: "tool_result",
                toolName: "web_search",
                toolInput: { max_results: 5, query: "recent US and Europe news" },
                toolOutput: JSON.stringify({
                  count: 2,
                  results: ["Reuters", "BBC"],
                }),
                status: "completed",
                success: true,
                startedAt: new Date().toISOString(),
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    const activity = screen.getByTestId("deepspace-activity-step");
    expect(activity).toHaveTextContent("Max Results: 5");
    expect(activity).toHaveTextContent("Query: recent US and Europe news");
    expect(activity).toHaveTextContent("Results:");
    expect(activity).not.toHaveTextContent('{"count":2');
  });

  it("shows a completed duration summary and keeps the full result expandable", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_timeline_complete_1",
            role: "assistant",
            content: "The summary is ready.",
            rawContent: "The summary is ready.",
            createdAt: "2026-08-19T10:00:00.000Z",
            status: "ready",
            timeline: [
              {
                id: "tool_result_1",
                stepId: "tool_result_1",
                turnIndex: 1,
                phase: "thinking",
                type: "tool_output",
                title: "Tool result",
                status: "completed",
                startedAt: "2026-08-19T10:00:00.000Z",
                completedAt: "2026-08-19T10:00:12.000Z",
                toolName: "web_search",
                toolOutput: JSON.stringify({
                  count: 2,
                  results: ["Reuters — AI policy", "BBC — AI research"],
                }),
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText("Worked for 12 seconds")).toBeInTheDocument();
    expect(screen.getAllByText("Tool result").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Count: 2/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Reuters — AI policy/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Worked for 12 seconds"));
    expect(screen.getByText("Thinking & activity")).toBeInTheDocument();
  });

  it("does not show the provider's transient pending_tool fragment as a duplicate", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_pending_tool_1",
            role: "assistant",
            content: "",
            rawContent: "",
            createdAt: new Date().toISOString(),
            status: "error",
            agentSteps: [
              {
                id: "pending_step",
                type: "tool_error",
                toolName: "pending_tool",
                toolOutput: "transient argument fragment",
                status: "failed",
                startedAt: new Date().toISOString(),
              },
              {
                id: "resolved_step",
                type: "tool_result",
                toolName: "todo_write",
                toolOutput: "10 tasks saved",
                status: "completed",
                success: true,
                startedAt: new Date().toISOString(),
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.queryByText("pending_tool")).not.toBeInTheDocument();
    expect(screen.getByText("todo_write")).toBeInTheDocument();
  });

  it("renders the live activity timeline in its actual streamed order", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_timeline_1",
            role: "assistant",
            content: "Finished answer",
            rawContent: "Finished answer",
            createdAt: new Date().toISOString(),
            status: "ready",
            timeline: [
              {
                id: "think_1",
                stepId: "think_1",
                turnIndex: 1,
                phase: "thinking",
                type: "thinking",
                title: "Internal Thought",
                status: "completed",
                startedAt: new Date().toISOString(),
                details: "I will create the list.",
              },
              {
                id: "tool_1",
                stepId: "tool_1",
                turnIndex: 1,
                phase: "modifying",
                type: "tool_call",
                title: "Write tasks",
                status: "completed",
                startedAt: new Date().toISOString(),
                toolName: "todo_write",
                toolInputStream: '{"tasks":[',
                toolOutput: "10 tasks saved",
              },
              {
                id: "think_2",
                stepId: "think_2",
                turnIndex: 2,
                phase: "thinking",
                type: "thinking",
                title: "Internal Thought",
                status: "completed",
                startedAt: new Date().toISOString(),
                details: "I can now summarize it.",
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    const steps = screen.getAllByTestId("deepspace-timeline-step");
    expect(steps.map((step) => step.textContent)).toEqual(
      expect.arrayContaining([
        expect.stringContaining("I will create the list."),
        expect.stringContaining("todo_write"),
        expect.stringContaining("I can now summarize it."),
      ]),
    );
    expect(steps[0]?.textContent).toContain("I will create the list.");
    expect(steps[1]?.textContent).toContain("todo_write");
    expect(steps[2]?.textContent).toContain("I can now summarize it.");
  });

  it("renders streamed thinking with the Markdown renderer instead of plain paragraph text", () => {
    markdownRendererMock.mockClear();
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_structured_thinking_1",
            role: "assistant",
            content: "",
            rawContent: "",
            createdAt: new Date().toISOString(),
            status: "streaming",
            timeline: [
              {
                id: "thinking_structured_1",
                stepId: "thinking_structured_1",
                turnIndex: 1,
                phase: "thinking",
                type: "thinking",
                title: "Internal Thought",
                status: "running",
                startedAt: new Date().toISOString(),
                details: "## Plan\n\n- Inspect the source\n- Summarize the result",
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(markdownRendererMock).toHaveBeenCalledWith(
      expect.objectContaining({
        content: "## Plan\n\n- Inspect the source\n- Summarize the result",
        streaming: true,
        compact: true,
      }),
    );
  });

  it("renders model activity messages as Markdown in the timeline", () => {
    markdownRendererMock.mockClear();
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_model_message_1",
            role: "assistant",
            content: "Final answer",
            rawContent: "Final answer",
            createdAt: new Date().toISOString(),
            status: "ready",
            timeline: [
              {
                id: "model_message_1",
                stepId: "model_message_1",
                turnIndex: 1,
                phase: "thinking",
                type: "model_message",
                title: "Model message",
                status: "completed",
                startedAt: new Date().toISOString(),
                details: "## Gmail status\n\n- Connection needs attention",
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(markdownRendererMock).toHaveBeenCalledWith(
      expect.objectContaining({
        content: "## Gmail status\n\n- Connection needs attention",
        compact: true,
      }),
    );
  });

  it("does not rerun the markdown renderer when local copy state changes", () => {
    markdownRendererMock.mockClear();
    const message = {
      id: "assistant_copy_1",
      role: "assistant" as const,
      content: "Copyable answer text",
      rawContent: "Copyable answer text",
      createdAt: new Date().toISOString(),
      status: "ready" as const,
    };

    const { rerender } = render(
      <DeepSpaceThread
        messages={[message]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(markdownRendererMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /copy/i }));
    expect(markdownRendererMock).toHaveBeenCalledTimes(1);

    rerender(
      <DeepSpaceThread
        messages={[message]}
        emptyPrompts={[]}
        onPromptSelect={() => undefined}
        onInsertLatestAnswer={() => undefined}
      />,
    );

    expect(markdownRendererMock).toHaveBeenCalledTimes(1);
  });

  it("renders an inline question card with selectable and custom answers", async () => {
    const onSubmitUserQuestion = vi.fn().mockResolvedValue(undefined);
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_question_1",
            role: "assistant",
            content: "Which format should I use?",
            rawContent: "Which format should I use?",
            createdAt: new Date().toISOString(),
            status: "ready",
            agentSteps: [
              {
                id: "question_step_1",
                type: "ask_user_question",
                toolName: "ask_user",
                toolId: "question-call-1",
                status: "awaiting_approval",
                startedAt: new Date().toISOString(),
                data: {
                  question_id: "question-1",
                  message: "Which format should I use?",
                  options: ["Markdown", "Plain text"],
                },
              },
            ],
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
        onSubmitUserQuestion={onSubmitUserQuestion}
      />,
    );

    expect(screen.getByLabelText("DeepSpace question")).toBeInTheDocument();
    expect(screen.getAllByText("Which format should I use?").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByText("Other / write my own answer")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Recommended Markdown/i }));
    await waitFor(() => expect(onSubmitUserQuestion).toHaveBeenCalledWith("Markdown"));
  });
});
