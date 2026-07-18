import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AgentStepPanel from "../app/dashboard/deepspace/_components/AgentStepPanel";
import type { AgentStep, TimelineStep } from "../app/dashboard/deepspace/_lib/deepspace-stream";

describe("AgentStepPanel collapse behavior", () => {
  it("keeps the clearance required box open until a decision is made, then displays the live progress", async () => {
    const onResume = vi.fn();
    const startedAt = new Date().toISOString();
    window.scrollTo = vi.fn();

    const initialSteps: AgentStep[] = [
      {
        id: "step-plan",
        type: "plan",
        plan: "Gather context",
        status: "completed",
        startedAt,
      },
      {
        id: "step-approval",
        type: "permission_request",
        stepId: "step-approval",
        toolName: "web_search",
        toolInput: { query: "alpha" },
        permissionLevel: "approval",
        status: "awaiting_approval",
        startedAt,
        step_id: "step-approval",
        tool_id: "tool-approval",
        data: { tier: 2 },
      },
    ];

    const resolvedSteps: AgentStep[] = [
      {
        ...initialSteps[0],
      },
      {
        ...initialSteps[1],
        type: "tool_start",
        status: "running",
        toolOutput: "searching",
      },
    ];

    const { rerender } = render(<AgentStepPanel steps={initialSteps} onResume={onResume} />);

    expect(await screen.findByText("clearance required (tier 2)")).toBeInTheDocument();
    expect(screen.getByText(/Clearance requested to execute:/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onResume).toHaveBeenCalledWith("step-approval", "tool-approval", true);

    rerender(<AgentStepPanel steps={resolvedSteps} onResume={onResume} />);

    await waitFor(() => {
      expect(screen.queryByText("clearance required (tier 2)")).not.toBeInTheDocument();
    });
  });

  it("submits clarification answers as a new prompt instead of a permission approval", async () => {
    const onClarifyAnswer = vi.fn();
    const startedAt = new Date().toISOString();

    render(
      <AgentStepPanel
        steps={[
          {
            id: "step-clarify",
            type: "ask_user_question",
            stepId: "step-clarify",
            toolName: "ask_user_question",
            toolInput: {},
            permissionLevel: "clarification",
            status: "awaiting_approval",
            startedAt,
            step_id: "step-clarify",
            tool_id: "tool-clarify",
            data: {
              questions: [
                {
                  header: "Topic/Text",
                  question: "Please provide the topic or text you would like me to explain simply.",
                  options: [
                    { label: "Explain a topic" },
                    { label: "Improve wording", description: "Rewrite more clearly" },
                  ],
                },
              ],
            },
          },
        ]}
        onClarifyAnswer={onClarifyAnswer}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Explain a topic/i }));

    expect(onClarifyAnswer).toHaveBeenCalledWith("Explain a topic");
  });

  it("renders stage labels instead of raw planning payloads in the timeline", () => {
    const startedAt = new Date().toISOString();
    const timeline: TimelineStep[] = [
      {
        id: "timeline-plan",
        stepId: "timeline-plan",
        turnIndex: 0,
        phase: "planning",
        type: "plan",
        title: "Strategic Plan",
        status: "completed",
        startedAt,
        details: "Plan the next move.",
      },
      {
        id: "timeline-clarify",
        stepId: "timeline-clarify",
        turnIndex: 0,
        phase: "exploring",
        type: "permission",
        title: "Clarification Needed",
        status: "awaiting_approval",
        startedAt,
        toolName: "ask_user_question",
        toolId: "tool-clarify",
        toolInput: {
          questions: [
            {
              header: "Topic/Text",
              question: "Please provide the topic or text you would like me to explain simply.",
              options: [{ label: "Explain a topic" }],
            },
          ],
        },
        data: {
          questions: [
            {
              header: "Topic/Text",
              question: "Please provide the topic or text you would like me to explain simply.",
              options: [{ label: "Explain a topic" }],
            },
          ],
        },
      },
    ];

    render(<AgentStepPanel steps={[]} timeline={timeline} isStreaming={false} />);

    expect(screen.getByText("Planning...")).toBeInTheDocument();
    expect(screen.getByText(/clarification required/i)).toBeInTheDocument();
    expect(
      screen.getAllByText(
        /Please provide the topic or text you would like me to explain simply\./i,
      ),
    ).toHaveLength(2);
    expect(screen.queryByText(/"questions"/i)).not.toBeInTheDocument();
  });

  it("renders a flat list of all steps chronologically", () => {
    const startedAt = new Date().toISOString();
    const onResume = vi.fn();
    const steps: AgentStep[] = Array.from({ length: 5 }, (_, index) => ({
      id: `step-${index + 1}`,
      type: index === 4 ? "tool_start" : "tool_result",
      stepId: `step-${index + 1}`,
      toolName: "read_file",
      toolInput: { index, path: "File" },
      toolOutput: `output-${index + 1}`,
      status: index === 4 ? "running" : "completed",
      startedAt,
      step_id: `step-${index + 1}`,
      tool_id: `tool-${index + 1}`,
      data: { tier: 2 },
    }));

    render(<AgentStepPanel steps={steps} onResume={onResume} />);

    expect(screen.getAllByText("File")).toHaveLength(5);
  });

  it("shows completed thought duration and renders markdown in the thought body", async () => {
    const startedAt = new Date("2026-06-21T18:23:00.000Z").toISOString();
    const completedAt = new Date("2026-06-21T18:23:12.000Z").toISOString();

    render(
      <AgentStepPanel
        steps={[
          {
            id: "step-think",
            type: "thinking",
            plan: "### Focus\n\n**Done**",
            toolOutput: "### Focus\n\n**Done**",
            status: "completed",
            startedAt,
            completedAt,
            durationMs: 12000,
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByText("Thought for 12s"));

    expect(await screen.findByRole("heading", { name: "Focus" })).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.queryByText(/### Focus/)).not.toBeInTheDocument();
  });

  it("renders todo ledger payloads as polished rich text instead of raw json", () => {
    const startedAt = new Date().toISOString();

    render(
      <AgentStepPanel
        steps={[
          {
            id: "step-todo",
            type: "tool_start",
            stepId: "step-todo",
            toolName: "todo_write",
            toolInput: {
              todos: [
                {
                  content: "**Task:** Generate a quantum physics assignment",
                  activeForm: "Generate the assignment",
                  status: "pending",
                },
                {
                  content: "Create the blog article in markdown",
                  activeForm: "Write the blog article",
                  status: "in_progress",
                },
              ],
            },
            toolOutput: "Proactive work ledger updated.",
            status: "completed",
            startedAt,
            step_id: "step-todo",
            tool_id: "tool-todo",
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByText("Updating Task Ledger"));

    expect(screen.getByText("Generate the assignment")).toBeInTheDocument();
    expect(screen.getByText("Write the blog article")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
    expect(screen.queryByText(/"todos"/i)).not.toBeInTheDocument();
  });

  it("does not render Turn headings and outputs flat list of steps", () => {
    const startedAt = new Date().toISOString();
    const onResume = vi.fn();
    const steps: AgentStep[] = [
      {
        id: "step-a",
        type: "tool_result",
        stepId: "step-a",
        toolName: "read_file",
        toolInput: { path: "/tmp/a.txt" },
        toolOutput: "a result",
        status: "completed",
        startedAt,
        step_id: "step-a",
        tool_id: "tool-a",
        turnIndex: 0,
      },
      {
        id: "step-b",
        type: "tool_result",
        stepId: "step-b",
        toolName: "read_file",
        toolInput: { path: "/tmp/b.txt" },
        toolOutput: "b result",
        status: "running",
        startedAt,
        step_id: "step-b",
        tool_id: "tool-b",
        turnIndex: 1,
      },
    ];

    render(<AgentStepPanel steps={steps} onResume={onResume} />);

    expect(screen.queryByText("Turn 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Turn 2")).not.toBeInTheDocument();
  });
});
