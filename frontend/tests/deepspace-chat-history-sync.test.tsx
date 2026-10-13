import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../app/context/AuthContext";
import DeepSpaceChatClient from "../app/dashboard/deepspace/_components/DeepSpaceChatClient";

const fetchWithAuthMock = vi.fn();
const startMock = vi.fn();
const queueEventHandler: {
  current: ((event: { data?: Record<string, unknown> }) => void) | null;
} = { current: null };

function renderChat(props: Partial<ComponentProps<typeof DeepSpaceChatClient>> = {}) {
  const { activeConversationId = null, ...rest } = props;
  return render(
    <AuthProvider>
      <DeepSpaceChatClient activeConversationId={activeConversationId} {...rest} />
    </AuthProvider>,
  );
}

async function waitForSelectedConversationReady() {
  await waitFor(() => {
    const composer = screen.getByLabelText("DeepSpace composer draft");
    expect(composer.closest("[aria-busy]")).toHaveAttribute("aria-busy", "false");
  });
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

vi.mock("@/lib/realtime", () => ({
  useRealtimeEvents: (
    handler: (event: { data?: Record<string, unknown> }) => void,
    resources: string[],
  ) => {
    if (resources.length === 1 && resources[0] === "queues") {
      queueEventHandler.current = handler;
    }
  },
}));

vi.mock("../app/dashboard/deepspace/_hooks/useDeepSpaceStream", () => ({
  useDeepSpaceStream: (options: {
    onEvent: (event: Record<string, unknown>) => void;
    onFinally?: () => void;
  }) => ({
    start: (...args: unknown[]) => startMock(options, ...args),
    cancel: vi.fn(),
    detach: vi.fn(),
    resume: vi.fn(),
  }),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceComposer", () => ({
  default: ({
    query,
    onQueryChange,
    onSubmit,
    showActiveResponseControls = false,
    queuedTurns = [],
    editingQueuedTurnId = null,
    onEditQueuedTurn,
    onCancelQueueEdit,
    onSaveQueueEdit,
    queuePaused = false,
    onResumeQueue,
    onRetryFailedTurn,
  }: {
    query: string;
    onQueryChange: (value: string) => void;
    onSubmit: () => void;
    showActiveResponseControls?: boolean;
    queuedTurns?: Array<{ clientRequestId: string; prompt: string; status?: string }>;
    editingQueuedTurnId?: string | null;
    onEditQueuedTurn?: (requestId: string) => void;
    onCancelQueueEdit?: () => void;
    onSaveQueueEdit?: (requestId: string, message: string) => Promise<boolean>;
    queuePaused?: boolean;
    onResumeQueue?: () => void;
    onRetryFailedTurn?: (requestId: string) => void;
  }) => (
    <div>
      <button type="button" onClick={() => onQueryChange("hi")}>
        Set Query
      </button>
      <textarea
        aria-label="DeepSpace composer draft"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
      />
      <button type="button" onClick={onSubmit}>
        Submit Query
      </button>
      <span data-testid="active-response-controls">{String(showActiveResponseControls)}</span>
      {editingQueuedTurnId ? (
        <>
          <button type="button" onClick={onCancelQueueEdit}>
            Cancel queue edit
          </button>
          <button type="button" onClick={() => void onSaveQueueEdit?.(editingQueuedTurnId, query)}>
            Save queue edit
          </button>
        </>
      ) : null}
      {queuePaused ? (
        <button type="button" onClick={onResumeQueue}>
          Resume queue
        </button>
      ) : null}
      <div data-testid="composer-queue">{queuedTurns.map((turn) => turn.prompt).join("|")}</div>
      {queuedTurns.map((turn) => (
        <span key={turn.clientRequestId}>
          <button type="button" onClick={() => onRetryFailedTurn?.(turn.clientRequestId)}>
            Retry {turn.clientRequestId}
          </button>
          {turn.status === "queued" ? (
            <button type="button" onClick={() => onEditQueuedTurn?.(turn.clientRequestId)}>
              Edit {turn.clientRequestId}
            </button>
          ) : null}
        </span>
      ))}
    </div>
  ),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceThread", () => ({
  default: ({
    messages,
    queuedAssistantId,
    onRegenerate,
    onActivateVersion,
    onSubmitUserQuestion,
  }: {
    messages: Array<{
      role: string;
      content: string;
      id: string;
      activeVersionIndex?: number;
      versionCount?: number;
      versions?: Array<{ id: string; version_index: number }>;
    }>;
    queuedAssistantId?: string | null;
    onRegenerate?: (messageId: string) => void;
    onActivateVersion?: (messageId: string, versionId: string) => void;
    onSubmitUserQuestion?: (answer: string) => Promise<void>;
  }) => (
    <div data-testid="deepspace-thread" data-queued-assistant={queuedAssistantId ?? ""}>
      {messages.map((message) => `${message.role}:${message.content}`).join("|")}
      {messages
        .filter((message) => message.role === "assistant" && (message.versionCount ?? 0) > 1)
        .map((message) => {
          const previousVersion = message.versions?.find(
            (version) => version.version_index === (message.activeVersionIndex ?? 1) - 1,
          );
          const nextVersion = message.versions?.find(
            (version) => version.version_index === (message.activeVersionIndex ?? 1) + 1,
          );
          return (
            <span key={message.id}>
              <button
                type="button"
                aria-label="Previous response version"
                disabled={!previousVersion}
                onClick={() =>
                  previousVersion && onActivateVersion?.(message.id, previousVersion.id)
                }
              >
                Previous response version
              </button>
              <span>
                {message.activeVersionIndex} / {message.versionCount}
              </span>
              <button
                type="button"
                aria-label="Next response version"
                disabled={!nextVersion}
                onClick={() => nextVersion && onActivateVersion?.(message.id, nextVersion.id)}
              >
                Next response version
              </button>
            </span>
          );
        })}
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    startMock.mockReset();
    queueEventHandler.current = null;

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

      if (url === "/deepspace/chats/conv-1/queue") {
        return { ok: true, json: async () => [] };
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

  it("clears the completion pulse timer when the chat unmounts", async () => {
    const setTimeoutSpy = vi.spyOn(window, "setTimeout");
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout");
    const view = renderChat({ activeConversationId: "conv-1" });

    await waitForSelectedConversationReady();
    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit Query" }));
    await waitFor(() => expect(startMock).toHaveBeenCalled());

    const completionPulseTimeoutIndex = setTimeoutSpy.mock.calls.findIndex(
      ([, delay]) => delay === 950,
    );
    expect(completionPulseTimeoutIndex).toBeGreaterThanOrEqual(0);
    const completionPulseTimeout = setTimeoutSpy.mock.results[completionPulseTimeoutIndex]?.value;
    expect(completionPulseTimeout).toBeDefined();

    view.unmount();

    expect(clearTimeoutSpy).toHaveBeenCalledWith(completionPulseTimeout);
  });

  it("keeps active-response controls hidden in a new empty chat", async () => {
    renderChat();
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    });

    expect(screen.getByTestId("active-response-controls")).toHaveTextContent("false");
  });

  it("does not render a decorative logo in an empty chat", async () => {
    renderChat();
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    });

    expect(screen.queryByRole("img", { name: "DeepSpace logo" })).not.toBeInTheDocument();
  });

  it("reloads the saved assistant reply after a blank stream finishes", async () => {
    let queuedRequestId: string | null = null;
    let streamFinished = false;
    fetchWithAuthMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return {
          ok: true,
          json: async () => ({
            messages: streamFinished
              ? [
                  {
                    id: "assistant-1",
                    role: "assistant",
                    content: "Saved DeepSpace answer.",
                    created_at: new Date().toISOString(),
                    metadata_json: {},
                  },
                ]
              : [],
          }),
        };
      }

      if (url === "/deepspace/chats/conv-1/queue" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as {
          client_request_id: string;
          regenerate_message_id: string;
        };
        queuedRequestId = body.client_request_id;
        return {
          ok: true,
          json: async () => ({
            client_request_id: body.client_request_id,
            regenerate_message_id: body.regenerate_message_id,
            prompt: "",
            priority: 0,
            sequence: 1,
            status: "running",
          }),
        };
      }

      if (url === "/deepspace/chats/conv-1/queue/state") {
        return {
          ok: true,
          json: async () => ({ paused: false, active_request_id: queuedRequestId }),
        };
      }

      if (url === "/deepspace/chats/conv-1/queue") {
        return { ok: true, json: async () => [] };
      }

      return { ok: true, json: async () => ({}) };
    });
    startMock.mockImplementationOnce(
      async (options: {
        onEvent: (event: Record<string, unknown>) => void;
        onFinally?: () => void;
      }) => {
        options.onEvent({
          event: "start",
          data: {
            message_id: "assistant-generated-1",
            conversation_id: "conv-1",
            started_at: new Date().toISOString(),
          },
        });
        streamFinished = true;
        options.onFinally?.();
      },
    );
    renderChat({ activeConversationId: "conv-1" });

    await waitFor(() => {
      expect(
        fetchWithAuthMock.mock.calls.some(([url]) => url === "/deepspace/chats/conv-1/messages"),
      ).toBe(true);
    });

    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toBeInTheDocument();
    });
    await waitForSelectedConversationReady();

    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));

    await waitFor(() => {
      expect(startMock).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toHaveTextContent(
        "assistant:Saved DeepSpace answer.",
      );
    });
  });

  it("switches saved response versions in click order and keeps the latest selection", async () => {
    const versions = [1, 2, 3].map((versionIndex) => ({
      id: `version-${versionIndex}`,
      version_index: versionIndex,
      content: `Saved response version ${versionIndex}.`,
      source_type: "assistant",
      created_at: new Date().toISOString(),
    }));
    let finishFirstActivation: ((response: unknown) => void) | null = null;
    let finishSecondActivation: ((response: unknown) => void) | null = null;
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return {
          ok: true,
          json: async () => ({
            messages: [
              {
                id: "assistant-versioned",
                role: "assistant",
                content: versions[2]!.content,
                created_at: new Date().toISOString(),
                active_version_id: "version-3",
                active_version_index: 3,
                version_count: 3,
                versions,
                metadata_json: {},
              },
            ],
          }),
        };
      }
      if (url.includes("/versions/version-2/activate")) {
        return new Promise((resolve) => {
          finishFirstActivation = resolve;
        });
      }
      if (url.includes("/versions/version-1/activate")) {
        return new Promise((resolve) => {
          finishSecondActivation = resolve;
        });
      }
      if (url === "/deepspace/chats/conv-1/queue") {
        return { ok: true, json: async () => [] };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });
    expect(await screen.findByText("assistant:Saved response version 3.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Previous response version" }));
    expect(screen.getByTestId("deepspace-thread")).toHaveTextContent(
      "assistant:Saved response version 2.",
    );
    await waitFor(() => expect(finishFirstActivation).toBeTypeOf("function"));

    fireEvent.click(screen.getByRole("button", { name: "Previous response version" }));
    expect(screen.getByTestId("deepspace-thread")).toHaveTextContent(
      "assistant:Saved response version 1.",
    );
    expect(finishSecondActivation).toBeNull();

    await act(async () => {
      finishFirstActivation?.({ ok: true, json: async () => ({ versions }) });
    });
    await waitFor(() => expect(finishSecondActivation).toBeTypeOf("function"));
    await act(async () => {
      finishSecondActivation?.({ ok: true, json: async () => ({ versions }) });
    });

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/deepspace/chats/conv-1/messages/assistant-versioned/versions/version-1/activate",
        { method: "PATCH" },
      );
      expect(screen.getByTestId("deepspace-thread")).toHaveTextContent(
        "assistant:Saved response version 1.",
      );
    });
  });

  it("keeps the old conversation read-only while the selected conversation loads", async () => {
    let resolveSelectedHistory:
      | ((response: {
          ok: boolean;
          json: () => Promise<{ messages: Array<Record<string, unknown>> }>;
        }) => void)
      | null = null;
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return {
          ok: true,
          json: async () => ({
            messages: [
              {
                id: "assistant-conv-1",
                role: "assistant",
                content: "First conversation stays saved.",
                created_at: new Date().toISOString(),
                metadata_json: {},
              },
            ],
          }),
        };
      }
      if (url === "/deepspace/chats/conv-2/messages") {
        return new Promise((resolve) => {
          resolveSelectedHistory = resolve;
        });
      }
      if (url.endsWith("/queue")) return { ok: true, json: async () => [] };
      return { ok: true, json: async () => ({}) };
    });

    const view = renderChat({ activeConversationId: "conv-1" });
    expect(
      await screen.findByText("assistant:First conversation stays saved."),
    ).toBeInTheDocument();

    view.rerender(
      <AuthProvider>
        <DeepSpaceChatClient activeConversationId="conv-2" />
      </AuthProvider>,
    );

    expect(await screen.findByRole("status")).toHaveTextContent("Loading selected conversation");
    expect(screen.getByTestId("deepspace-thread")).toHaveTextContent(
      "assistant:First conversation stays saved.",
    );
    expect(screen.getByTestId("deepspace-thread").parentElement).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(view.container.querySelector(".deepspace-scroll-tracker")).toHaveAttribute("inert");

    const composer = view.container.querySelector('[aria-busy="true"][aria-hidden="true"]');
    expect(composer).toHaveAttribute("inert");
    fireEvent.click(composer!.querySelector("button")!);
    fireEvent.click(composer!.querySelectorAll("button")[1]!);
    expect(startMock).not.toHaveBeenCalled();

    await act(async () => {
      resolveSelectedHistory?.({
        ok: true,
        json: async () => ({
          messages: [
            {
              id: "assistant-conv-2",
              role: "assistant",
              content: "Second conversation is loaded.",
              created_at: new Date().toISOString(),
              metadata_json: {},
            },
          ],
        }),
      });
    });

    expect(await screen.findByText("assistant:Second conversation is loaded.")).toBeInTheDocument();
    expect(screen.queryByText("Loading selected conversation…")).not.toBeInTheDocument();
    expect(view.container.querySelector(".deepspace-scroll-tracker")).not.toHaveAttribute("inert");
  });

  it("restores the server-selected response version when saving a switch fails", async () => {
    const versions = [1, 2].map((versionIndex) => ({
      id: `version-${versionIndex}`,
      version_index: versionIndex,
      content: `Saved response version ${versionIndex}.`,
      source_type: "assistant",
      created_at: new Date().toISOString(),
    }));
    let historyLoads = 0;
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        historyLoads += 1;
        return {
          ok: true,
          json: async () => ({
            messages: [
              {
                id: "assistant-versioned",
                role: "assistant",
                content: versions[1]!.content,
                created_at: new Date().toISOString(),
                active_version_id: "version-2",
                active_version_index: 2,
                version_count: 2,
                versions,
                metadata_json: {},
              },
            ],
          }),
        };
      }
      if (url.includes("/versions/version-1/activate"))
        return { ok: false, json: async () => ({}) };
      if (url === "/deepspace/chats/conv-1/queue") {
        return { ok: true, json: async () => [] };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });
    expect(await screen.findByText("assistant:Saved response version 2.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous response version" }));

    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toHaveTextContent(
        "assistant:Saved response version 2.",
      );
      expect(historyLoads).toBeGreaterThan(1);
    });
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      "/deepspace/chats/conv-1/messages/assistant-versioned/versions/version-1/activate",
      { method: "PATCH" },
    );
  });

  it("shows the selected conversation's existing ID in expanded diagnostics", async () => {
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/operational-summary") {
        return {
          ok: true,
          json: async () => ({
            sample_size: 1,
            failure_rate: 0,
            p50_latency_ms: 220,
            p95_latency_ms: 220,
            providers: [
              {
                provider: "openai:gpt-4.1",
                sample_size: 1,
                failure_rate: 0,
                p50_latency_ms: 220,
                p95_latency_ms: 220,
              },
            ],
          }),
        };
      }
      if (url === "/deepspace/chats/conv-1/messages") {
        return { ok: true, json: async () => ({ messages: [] }) };
      }
      if (url === "/deepspace/chats/conv-1/queue") {
        return { ok: true, json: async () => [] };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });

    const disclosure = await screen.findByText(/Provider health/);
    fireEvent.click(disclosure.closest("summary")!);

    expect(await screen.findByText("conv-1")).toBeInTheDocument();
    expect(fetchWithAuthMock).not.toHaveBeenCalledWith(
      "/deepspace/chats",
      expect.objectContaining({ method: "POST" }),
    );
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
      if (url === "/deepspace/chats/conv-1/queue") {
        return {
          ok: true,
          json: async () => [
            {
              client_request_id: "request-running-1",
              prompt: "Search recent reports",
              priority: 0,
              sequence: 1,
              status: "queued",
            },
          ],
        };
      }
      return { ok: true, json: async () => ({}) };
    });
    startMock.mockImplementationOnce(async () => {});

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
    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toHaveAttribute(
        "data-queued-assistant",
        "assistant-running-1",
      );
      expect(screen.getByTestId("composer-queue")).not.toHaveTextContent("Search recent reports");
      expect(screen.getByTestId("active-response-controls")).toHaveTextContent("true");
    });
  });

  it("keeps the active queued prompt in the thread instead of listing it twice", async () => {
    let queueRows: Array<Record<string, unknown>> = [];
    let requestId = "";
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return { ok: true, json: async () => ({ messages: [] }) };
      }
      if (url === "/deepspace/chats/conv-1/queue") {
        return { ok: true, json: async () => queueRows };
      }
      return { ok: true, json: async () => ({}) };
    });
    startMock.mockImplementationOnce(
      async (_options: unknown, request: { body: { client_request_id: string } }) => {
        requestId = request.body.client_request_id;
      },
    );

    renderChat({ activeConversationId: "conv-1" });
    await waitFor(() => expect(screen.getByTestId("deepspace-thread")).toBeInTheDocument());
    await waitForSelectedConversationReady();
    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit Query" }));

    await waitFor(() => {
      expect(startMock).toHaveBeenCalled();
    });
    expect(requestId).toBeTruthy();
    expect(queueEventHandler.current).toBeTypeOf("function");

    queueRows = [
      {
        client_request_id: requestId,
        prompt: "hi",
        priority: 0,
        sequence: 1,
        status: "queued",
      },
      {
        client_request_id: "later-request",
        prompt: "Another queued prompt",
        priority: 0,
        sequence: 2,
        status: "queued",
      },
    ];
    act(() => queueEventHandler.current?.({ data: { conversation_id: "conv-1" } }));

    await waitFor(() => {
      expect(
        screen.getByTestId("deepspace-thread").getAttribute("data-queued-assistant"),
      ).toBeTruthy();
      expect(screen.getByTestId("composer-queue")).toHaveTextContent("Another queued prompt");
    });
    expect(screen.getByTestId("deepspace-thread")).toHaveTextContent("user:hi");
    expect(screen.getByTestId("composer-queue")).not.toHaveTextContent("hi");

    queueRows = [queueRows[1]!];
    act(() => queueEventHandler.current?.({ data: { conversation_id: "conv-1" } }));

    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toHaveAttribute("data-queued-assistant", "");
      expect(screen.getByTestId("composer-queue")).toHaveTextContent("Another queued prompt");
    });
  });

  it("refreshes queue events for a conversation created by the stream", async () => {
    let queueRows: Array<Record<string, unknown>> = [];
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/queue") {
        return { ok: true, json: async () => queueRows };
      }
      return { ok: true, json: async () => ({}) };
    });
    startMock.mockImplementationOnce(
      async (options: { onEvent: (event: Record<string, unknown>) => void }) => {
        options.onEvent({
          event: "start",
          data: {
            message_id: "assistant-created-1",
            conversation_id: "conv-1",
            started_at: new Date().toISOString(),
          },
        });
      },
    );

    renderChat();
    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit Query" }));

    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toHaveAttribute("data-queued-assistant", "");
    });
    queueRows = [
      {
        client_request_id: "follow-up-request",
        prompt: "Follow-up while the worker runs",
        priority: 0,
        sequence: 1,
        status: "queued",
      },
    ];
    act(() => queueEventHandler.current?.({ data: { conversation_id: "conv-1" } }));

    await waitFor(() => {
      expect(screen.getByTestId("composer-queue")).toHaveTextContent(
        "Follow-up while the worker runs",
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
    await waitForSelectedConversationReady();
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

    await waitForSelectedConversationReady();
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

  it("resumes the queue and reconnects to the next queued request", async () => {
    let queueIsPaused = true;
    fetchWithAuthMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return { ok: true, json: async () => ({ messages: [] }) };
      }
      if (url === "/deepspace/chats/conv-1/queue") {
        return {
          ok: true,
          json: async () => [
            {
              client_request_id: "queued-next",
              prompt: "Run the first pending prompt",
              priority: 0,
              sequence: 1,
              status: "queued",
            },
          ],
        };
      }
      if (url === "/deepspace/chats/conv-1/queue/state") {
        return {
          ok: true,
          json: async () => ({
            paused: queueIsPaused,
            active_request_id: queueIsPaused ? null : "queued-next",
          }),
        };
      }
      if (url === "/deepspace/chats/conv-1/queue/resume" && init?.method === "POST") {
        queueIsPaused = false;
        return {
          ok: true,
          json: async () => ({ paused: false, active_request_id: "queued-next" }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });
    fireEvent.click(await screen.findByRole("button", { name: "Resume queue" }));

    await waitFor(() => {
      expect(startMock).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          body: expect.objectContaining({
            conversation_id: "conv-1",
            client_request_id: "queued-next",
            reconnect: true,
          }),
        }),
      );
    });
    expect(startMock).toHaveBeenCalledTimes(1);
  });

  it("edits a queued prompt through PATCH and keeps it in its original FIFO slot", async () => {
    const queueRows = [
      {
        client_request_id: "first-request",
        prompt: "First queued prompt",
        priority: 0,
        sequence: 1,
        status: "queued",
      },
      {
        client_request_id: "middle-request",
        prompt: "Original middle prompt",
        priority: 0,
        sequence: 2,
        status: "queued",
      },
      {
        client_request_id: "last-request",
        prompt: "Last queued prompt",
        priority: 0,
        sequence: 3,
        status: "queued",
      },
    ];
    fetchWithAuthMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return { ok: true, json: async () => ({ messages: [] }) };
      }
      if (url === "/deepspace/chats/conv-1/queue" && !init?.method) {
        return { ok: true, json: async () => queueRows };
      }
      if (url === "/deepspace/chats/conv-1/queue/middle-request" && init?.method === "PATCH") {
        const body = JSON.parse(String(init.body)) as { message: string; expected_prompt: string };
        expect(body).toEqual({
          message: "Revised middle prompt",
          expected_prompt: "Original middle prompt",
        });
        return {
          ok: true,
          json: async () => ({
            ...queueRows[1],
            prompt: body.message,
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });
    fireEvent.click(await screen.findByRole("button", { name: "Set Query" }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit middle-request" }));

    const composer = screen.getByRole("textbox", { name: "DeepSpace composer draft" });
    expect(composer).toHaveValue("Original middle prompt");
    fireEvent.change(composer, { target: { value: "Revised middle prompt" } });
    fireEvent.click(screen.getByRole("button", { name: "Save queue edit" }));

    await waitFor(() => {
      expect(screen.getByTestId("composer-queue")).toHaveTextContent(
        "First queued prompt|Revised middle prompt|Last queued prompt",
      );
      expect(composer).toHaveValue("hi");
    });
    expect(
      fetchWithAuthMock.mock.calls.some(
        ([url, init]) =>
          url === "/deepspace/chats/conv-1/queue/middle-request" && init?.method === "PATCH",
      ),
    ).toBe(true);
    expect(startMock).not.toHaveBeenCalled();
  });
});
