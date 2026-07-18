import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DeepSpaceChatClient from "../app/dashboard/deepspace/_components/DeepSpaceChatClient";

const fetchWithAuthMock = vi.fn();
const estimateTokensMock = vi.fn((...args: [string]) => {
  void args;
  return 1;
});

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("../app/dashboard/query/_lib/stream-protocol", () => ({
  estimateTokens: (value: string) => estimateTokensMock(value),
}));

vi.mock("../app/dashboard/deepspace/_hooks/useDeepSpaceStream", () => ({
  useDeepSpaceStream: () => ({
    start: vi.fn(),
    cancel: vi.fn(),
    resume: vi.fn(),
  }),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceComposer", () => ({
  default: () => null,
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceThread", () => ({
  default: () => null,
}));

vi.mock("../app/components/dashboard/ChatSidebar", () => ({
  default: () => null,
}));

vi.mock("../app/dashboard/query/_components/DeepSpaceScrollTracker", () => ({
  default: () => null,
}));

vi.mock("../app/dashboard/deepspace/_components/AgentCapabilities", () => ({
  default: () => null,
}));

vi.mock("../app/dashboard/deepspace/_components/ExecutionModeDropdown", () => ({
  default: () => null,
}));

vi.mock("../app/dashboard/deepspace/_components/RuntimePreferencesDropdown", () => ({
  default: () => null,
}));

describe("DeepSpaceChatClient token estimation", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    estimateTokensMock.mockClear();

    const largeHistory = Array.from({ length: 100 }, (_, index) => ({
      id: `assistant-${index + 1}`,
      role: "assistant",
      content: `Answer ${index + 1}`,
      rawContent: `Answer ${index + 1}`,
      created_at: new Date().toISOString(),
      status: "ready",
    }));

    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-large/messages") {
        return {
          ok: true,
          json: async () => ({ messages: largeHistory }),
        };
      }

      if (url === "/deepspace/chats/runtime-preferences?conversation_id=conv-large") {
        return {
          ok: true,
          json: async () => ({
            execution_mode: "auto_review",
            planner_mode: "default",
            subagent_profile: "default",
            runtime_hooks_enabled: true,
            workspace_mode_enabled: true,
          }),
        };
      }

      return { ok: true, json: async () => ({}) };
    });
  });

  it("limits token estimation to the recent history window for large conversations", async () => {
    const onMetricsUpdate = vi.fn();

    render(
      <DeepSpaceChatClient activeConversationId="conv-large" onMetricsUpdate={onMetricsUpdate} />,
    );

    await waitFor(() => {
      expect(
        fetchWithAuthMock.mock.calls.some(
          ([url]) => url === "/deepspace/chats/conv-large/messages",
        ),
      ).toBe(true);
    });

    await waitFor(() => {
      expect(estimateTokensMock.mock.calls.length).toBe(66);
    });
    expect(onMetricsUpdate).toHaveBeenCalled();
  });
});
