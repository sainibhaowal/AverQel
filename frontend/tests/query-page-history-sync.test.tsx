import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import QueryPageClient from "../app/dashboard/query/_components/QueryPageClient";

const fetchWithAuthMock = vi.fn();
const startMock = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({
    get: () => null,
  }),
}));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("../app/dashboard/query/_hooks/useQueryStream", () => ({
  useQueryStream: (options: {
    onEvent: (event: Record<string, unknown>) => void;
    onFinally?: () => void;
  }) => ({
    start: (...args: unknown[]) => startMock(options, ...args),
    cancel: vi.fn(),
  }),
}));

vi.mock("../app/dashboard/query/_components/QueryComposer", () => ({
  default: ({
    onQueryChange,
    onSubmit,
  }: {
    onQueryChange: (value: string) => void;
    onSubmit: () => void;
  }) => (
    <div>
      <button type="button" onClick={() => onQueryChange("why is query blank")}>
        Set Query
      </button>
      <button type="button" onClick={onSubmit}>
        Submit Query
      </button>
    </div>
  ),
}));

vi.mock("../app/dashboard/query/_components/MessageThread", () => ({
  default: ({ messages }: { messages: Array<{ role: string; content: string }> }) => (
    <div data-testid="message-thread">{messages.map((message) => message.role).join(",")}</div>
  ),
}));

vi.mock("../app/dashboard/query/_components/DeepSpaceScrollTracker", () => ({
  default: () => null,
}));

vi.mock("@/app/components/dashboard/ChatSidebar", () => ({
  default: () => null,
}));

vi.mock("@/app/components/query/PDFPreviewModal", () => ({
  default: () => null,
}));

describe("QueryPageClient history sync", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    startMock.mockReset();

    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/queries/capabilities/chat") {
        return { ok: true, json: async () => ({ supports_thinking: false }) };
      }
      if (url === "/collections") {
        return { ok: true, json: async () => [] };
      }
      if (url === "/chats/conv-1/messages") {
        return { ok: true, json: async () => ({ messages: [{ id: "user-1", role: "user" }] }) };
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
            message_id: "server-assistant-1",
            conversation_id: "conv-1",
            started_at: new Date().toISOString(),
            operation: "new_turn",
          },
        });
        options.onEvent({
          event: "error",
          data: {
            code: "STREAM_EMPTY_PROVIDER_RESPONSE",
            message: "The chat model did not return an answer.",
          },
        });
        options.onFinally?.();
      },
    );
  });

  it("keeps the local stream error visible instead of overwriting it with empty history", async () => {
    render(<QueryPageClient />);

    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit Query" }));

    await waitFor(() => {
      expect(screen.getByText("The chat model did not return an answer.")).toBeInTheDocument();
    });

    expect(fetchWithAuthMock).not.toHaveBeenCalledWith("/chats/conv-1/messages");
  });
});
