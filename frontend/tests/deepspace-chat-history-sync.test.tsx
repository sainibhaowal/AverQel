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
  }: {
    onQueryChange: (value: string) => void;
    onSubmit: () => void;
  }) => (
    <div>
      <button type="button" onClick={() => onQueryChange("hi")}>
        Set Query
      </button>
      <button type="button" onClick={onSubmit}>
        Submit Query
      </button>
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

describe("DeepSpaceChatClient history sync", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    startMock.mockReset();

    fetchWithAuthMock.mockImplementation(async (url: string) => {
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
                metadata_json: {},
              },
            ],
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
});
