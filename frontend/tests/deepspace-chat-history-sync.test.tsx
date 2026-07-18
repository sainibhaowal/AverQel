import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DeepSpaceChatClient from "../app/dashboard/deepspace/_components/DeepSpaceChatClient";

const fetchWithAuthMock = vi.fn();
const startMock = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("../app/dashboard/deepspace/_hooks/useDeepSpaceStream", () => ({
  useDeepSpaceStream: (options: {
    onEvent: (event: Record<string, unknown>) => void;
    onFinally?: () => void;
  }) => ({
    start: (...args: unknown[]) => startMock(options, ...args),
    cancel: vi.fn(),
    resume: vi.fn(),
  }),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceComposer", () => ({
  default: ({
    onQueryChange,
    onSubmit,
    onRuntimePreferencesChange,
  }: {
    onQueryChange: (value: string) => void;
    onSubmit: () => void;
    onRuntimePreferencesChange?: (val: Record<string, unknown>) => void;
  }) => (
    <div>
      <button type="button" onClick={() => onQueryChange("hi")}>
        Set Query
      </button>
      <button type="button" onClick={onSubmit}>
        Submit Query
      </button>
      {onRuntimePreferencesChange && (
        <button
          type="button"
          onClick={() => onRuntimePreferencesChange({ planner_mode: "structured" })}
        >
          Update Runtime Preferences
        </button>
      )}
    </div>
  ),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceThread", () => ({
  default: ({
    messages,
    onRegenerate,
  }: {
    messages: Array<{ role: string; content: string; id: string }>;
    onRegenerate?: (messageId: string) => void;
  }) => (
    <div data-testid="deepspace-thread">
      {messages.map((message) => `${message.role}:${message.content}`).join("|")}
      <button type="button" onClick={() => onRegenerate?.(messages[0]?.id ?? "assistant-1")}>
        Regenerate
      </button>
    </div>
  ),
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

vi.mock("../app/dashboard/deepspace/_components/RuntimePreferencesDropdown", () => ({
  default: ({
    onChange,
  }: {
    onChange?: (value: {
      planner_mode?: "default" | "structured";
      runtime_hooks_enabled?: boolean;
    }) => void;
  }) => (
    <button type="button" onClick={() => onChange?.({ planner_mode: "structured" })}>
      Update Runtime Preferences
    </button>
  ),
}));

describe("DeepSpaceChatClient history sync", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    startMock.mockReset();

    fetchWithAuthMock.mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return {
          ok: true,
          json: async () => ({
            messages: [
              {
                id: "assistant-1",
                role: "assistant",
                content: "Saved DeepSpace answer.",
                created_at: new Date().toISOString(),
                metadata_json: {
                  conversation_compaction: {
                    version: 1,
                    trigger: "manual",
                    compacted_at: new Date().toISOString(),
                    anchor_message_id: "assistant-1",
                    summary: "Compacted conversation history:\n- User: earlier context",
                    summarized_count: 5,
                    kept_recent_count: 8,
                    before_tokens: 4200,
                    after_tokens: 1600,
                    saved_tokens: 2600,
                  },
                },
              },
            ],
          }),
        };
      }

      if (url === "/deepspace/chats/runtime-preferences?conversation_id=conv-1") {
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

      if (url === "/deepspace/chats/runtime-preferences" && options?.method === "PATCH") {
        return {
          ok: true,
          json: async () => ({
            execution_mode: "auto_review",
            planner_mode: "structured",
            subagent_profile: "default",
            runtime_hooks_enabled: true,
            workspace_mode_enabled: true,
          }),
        };
      }

      return { ok: true, json: async () => ({}) };
    });

    startMock.mockImplementation(
      async (options: {
        onEvent: (event: Record<string, unknown>) => void;
        onFinally?: () => void;
      }) => {
        options.onEvent({
          event: "start",
          data: {
            message_id: "assistant-1",
            conversation_id: "conv-1",
            started_at: new Date().toISOString(),
          },
        });
        options.onFinally?.();
      },
    );
  });

  it("reloads the saved assistant reply after a blank stream finishes", async () => {
    render(<DeepSpaceChatClient activeConversationId="conv-1" />);

    await waitFor(() => {
      expect(
        fetchWithAuthMock.mock.calls.some(([url]) => url === "/deepspace/chats/conv-1/messages"),
      ).toBe(true);
    });

    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));

    await waitFor(() => {
      expect(startMock).toHaveBeenCalled();
    });
  });

  it("reports usage metrics for loaded history", async () => {
    const onMetricsUpdate = vi.fn();

    render(<DeepSpaceChatClient activeConversationId="conv-1" onMetricsUpdate={onMetricsUpdate} />);

    await waitFor(() => {
      expect(onMetricsUpdate).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(
        onMetricsUpdate.mock.calls.some(
          ([metrics]) => (metrics as { tokens?: number }).tokens === 1600,
        ),
      ).toBe(true);
    });
  });

  it("persists runtime control changes through the runtime preferences endpoint", async () => {
    render(<DeepSpaceChatClient activeConversationId="conv-1" />);

    await waitFor(() => {
      expect(
        fetchWithAuthMock.mock.calls.some(
          ([url]) => url === "/deepspace/chats/runtime-preferences?conversation_id=conv-1",
        ),
      ).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: /update runtime preferences/i }));

    await waitFor(() => {
      expect(
        fetchWithAuthMock.mock.calls.some(
          ([url, options]) =>
            url === "/deepspace/chats/runtime-preferences" && options?.method === "PATCH",
        ),
      ).toBe(true);
    });
  });
});
