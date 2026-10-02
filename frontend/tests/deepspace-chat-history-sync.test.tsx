import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../app/context/AuthContext";
import DeepSpaceChatClient from "../app/dashboard/deepspace/_components/DeepSpaceChatClient";

const fetchWithAuthMock = vi.fn();
const startMock = vi.fn();

function renderChat(props: Partial<ComponentProps<typeof DeepSpaceChatClient>> = {}) {
  const { activeConversationId = null, ...rest } = props;
  return render(
    <AuthProvider>
      <DeepSpaceChatClient activeConversationId={activeConversationId} {...rest} />
    </AuthProvider>,
  );
}

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
  isDesktopEnvironment: () => false,
  getAccessTokenExpiry: () => null,
}));

vi.mock("@/lib/providers-api", () => ({
  listProviders: vi.fn(async () => []),
  listProviderModels: vi.fn(async () => []),
  refreshProviderModels: vi.fn(async () => []),
  listAssignments: vi.fn(async () => []),
  createAssignment: vi.fn(),
  updateAssignment: vi.fn(),
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
    onSubmitUserQuestion,
  }: {
    messages: Array<{ role: string; content: string; id: string }>;
    onRegenerate?: (messageId: string) => void;
    onSubmitUserQuestion?: (answer: string) => Promise<void>;
  }) => (
    <div data-testid="deepspace-thread">
      {messages.map((message) => `${message.role}:${message.content}`).join("|")}
      <button type="button" onClick={() => onRegenerate?.(messages[0]?.id ?? "assistant-1")}>
        Regenerate
      </button>
      <button type="button" onClick={() => void onSubmitUserQuestion?.("Markdown")}>
        Answer Clarification
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
    renderChat({ activeConversationId: "conv-1" });

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

  it("reconnects to an active durable run after a page reload without starting a second run", async () => {
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return {
          ok: true,
          json: async () => ({
            messages: [
              {
                id: "user-running-1",
                role: "user",
                content: "Search recent reports",
                created_at: new Date().toISOString(),
                metadata_json: {},
              },
              {
                id: "assistant-running-1",
                role: "assistant",
                content: "",
                created_at: new Date().toISOString(),
                metadata_json: {
                  status: "streaming",
                  runtime_active: true,
                  client_request_id: "request-running-1",
                },
              },
            ],
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });

    await waitFor(() => {
      expect(startMock).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          body: expect.objectContaining({
            conversation_id: "conv-1",
            client_request_id: "request-running-1",
            reconnect: true,
          }),
        }),
      );
    });
  });

  it("never treats a normal composer message as an answer to an older clarification", async () => {
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return {
          ok: true,
          json: async () => ({
            messages: [
              {
                id: "assistant-question-1",
                role: "assistant",
                content: "Which format should I use?",
                created_at: new Date().toISOString(),
                metadata_json: {
                  status: "awaiting_user",
                  pending_user_question: {
                    question_id: "question-1",
                    message: "Which format should I use?",
                  },
                  agent_steps: [
                    {
                      id: "question-step-1",
                      type: "ask_user_question",
                      status: "awaiting_approval",
                      data: {
                        question_id: "question-1",
                        message: "Which format should I use?",
                      },
                    },
                  ],
                },
              },
            ],
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });

    await waitFor(() => expect(screen.getByTestId("deepspace-thread")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit Query" }));

    await waitFor(() => {
      expect(startMock).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          body: expect.objectContaining({ message: "hi", conversation_id: "conv-1" }),
        }),
      );
    });
    const body = startMock.mock.calls.at(-1)?.[1]?.body as Record<string, unknown>;
    expect(body.resume_user_question_id).toBeUndefined();
  });

  it("resumes a clarification only from its explicit answer control", async () => {
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return {
          ok: true,
          json: async () => ({
            messages: [
              {
                id: "assistant-question-1",
                role: "assistant",
                content: "Which format should I use?",
                created_at: new Date().toISOString(),
                metadata_json: {
                  status: "awaiting_user",
                  pending_user_question: {
                    question_id: "question-1",
                    message: "Which format should I use?",
                  },
                  agent_steps: [
                    {
                      id: "question-step-1",
                      type: "ask_user_question",
                      status: "awaiting_approval",
                      data: { question_id: "question-1", message: "Which format should I use?" },
                    },
                  ],
                },
              },
            ],
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });
    await waitFor(() => expect(screen.getByTestId("deepspace-thread")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Answer Clarification" }));

    await waitFor(() => {
      expect(startMock).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          body: expect.objectContaining({
            message: "Markdown",
            resume_user_question_id: "question-1",
          }),
        }),
      );
    });
  });

  it("forwards streamed write-tool markdown to the live note preview and commits the saved note", async () => {
    const onAgentNotePreview = vi.fn();
    const onAgentNoteCommitted = vi.fn();
    startMock.mockImplementationOnce(
      async (options: {
        onEvent: (event: Record<string, unknown>) => void;
        onFinally?: () => void;
      }) => {
        options.onEvent({
          event: "start",
          data: { message_id: "assistant-1", conversation_id: "conv-1" },
        });
        options.onEvent({
          event: "tool_delta",
          data: {
            step_id: "tool_stream_1_0",
            tool_name: "write",
            text: '{"markdown":"# Live',
          },
        });
        options.onEvent({
          event: "tool_delta",
          data: {
            step_id: "tool_stream_1_0",
            tool_name: "write",
            text: ' note","mode":"replace"}',
          },
        });
        options.onEvent({
          event: "tool_result",
          data: {
            step_id: "tool_stream_1_0",
            tool_name: "write",
            output: JSON.stringify({ content_html: "<h1>Live note</h1>" }),
          },
        });
        options.onEvent({ event: "done", data: {} });
        options.onFinally?.();
      },
    );

    renderChat({
      activeConversationId: "conv-1",
      onAgentNotePreview,
      onAgentNoteCommitted,
    });

    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit Query" }));

    await waitFor(() => {
      expect(onAgentNotePreview).toHaveBeenLastCalledWith({
        conversationId: "conv-1",
        markdown: "# Live note",
        mode: "replace",
        status: "streaming",
      });
      expect(onAgentNoteCommitted).toHaveBeenCalledWith({
        conversationId: "conv-1",
        contentHtml: "<h1>Live note</h1>",
      });
    });
  });
});
