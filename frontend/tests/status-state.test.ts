import { describe, expect, it } from "vitest";

import { deriveAIStatusFromStep } from "@/app/dashboard/deepspace/stateManagement";

describe("deriveAIStatusFromStep", () => {
  it("maps a running thinking step to a thinking status", () => {
    const status = deriveAIStatusFromStep({
      type: "thinking",
      status: "running",
      startedAt: new Date().toISOString(),
      plan: "Thinking through the task",
    });

    expect(status.type).toBe("thinking");
    expect(status.message).toBe("Thinking");
  });

  it("maps search tools to searching", () => {
    const status = deriveAIStatusFromStep({
      type: "tool_start",
      status: "running",
      toolName: "web_search",
      startedAt: new Date().toISOString(),
    });

    expect(status.type).toBe("searching");
    expect(status.message).toBe("Searching");
  });

  it("formats completed thought durations", () => {
    const startedAt = new Date("2026-06-21T18:23:00.000Z").toISOString();
    const completedAt = new Date("2026-06-21T18:23:12.000Z").toISOString();
    const status = deriveAIStatusFromStep({
      type: "thinking",
      status: "completed",
      startedAt,
      completedAt,
      durationMs: 12000,
    });

    expect(status.type).toBe("completed");
    expect(status.message).toBe("Thought for 12s");
  });
});
