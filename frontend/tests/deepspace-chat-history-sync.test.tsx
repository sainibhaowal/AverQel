import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../app/context/AuthContext";
import DeepSpaceChatClient from "../app/dashboard/deepspace/_components/DeepSpaceChatClient";

const fetchWithAuthMock = vi.fn();
const startMock = vi.fn();
const cancelMock = vi.fn();
const queueEventHandler: {
  current: ((event: { data?: Record<string, unknown> }) => void) | null;
} = { current: null };
const voiceRoomMock = vi.hoisted(() => {
  type LiveKitMockHandler = (...args: unknown[]) => void;
  const handlers = new Map<string, LiveKitMockHandler>();
  const localParticipant = {
    setMicrophoneEnabled: vi.fn(async () => undefined),
    publishData: vi.fn(async (data: Uint8Array, options?: Record<string, unknown>) => {
      void data;
      void options;
    }),
  };
  return {
    handlers,
    localParticipant,
    remoteParticipants: new Map(),
    on: vi.fn((event: string, handler: LiveKitMockHandler) => {
      handlers.set(event, handler);
    }),
    off: vi.fn((event: string) => {
      handlers.delete(event);
    }),
    startAudio: vi.fn(async () => undefined),
    connect: vi.fn(async () => undefined),
    disconnect: vi.fn(),
  };
});

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

vi.mock("livekit-client", () => ({
  Room: vi.fn(() => voiceRoomMock),
  RoomEvent: {
    DataReceived: "dataReceived",
    TrackSubscribed: "trackSubscribed",
    TrackUnsubscribed: "trackUnsubscribed",
    ParticipantConnected: "participantConnected",
  },
}));

vi.mock("../app/dashboard/deepspace/_hooks/useDeepSpaceStream", () => ({
  useDeepSpaceStream: (options: {
    onEvent: (event: Record<string, unknown>) => void;
    onTransportError?: (error: { code: string; message: string }) => void;
    onFinally?: () => void;
    onUserCancel?: () => void;
  }) => ({
    start: (...args: unknown[]) => startMock(options, ...args),
    cancel: (...args: unknown[]) => {
      cancelMock(...args);
      options.onUserCancel?.();
    },
    detach: vi.fn(),
    resume: vi.fn(),
  }),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceComposer", () => ({
  default: ({
    query,
    isStreaming = false,
    stopping = false,
    onQueryChange,
    onSubmit,
    onStop,
    showActiveResponseControls = false,
    queuedTurns = [],
    editingQueuedTurnId = null,
    onEditQueuedTurn,
    onCancelQueueEdit,
    onSaveQueueEdit,
    queuePaused = false,
    onResumeQueue,
    onRetryFailedTurn,
    onSteerQueuedTurn,
    sttActive = false,
    ttsActive = false,
    onSttToggle,
    onTtsToggle,
  }: {
    query: string;
    isStreaming?: boolean;
    stopping?: boolean;
    onQueryChange: (value: string) => void;
    onSubmit: () => void;
    onStop: () => void;
    showActiveResponseControls?: boolean;
    queuedTurns?: Array<{ clientRequestId: string; prompt: string; status?: string }>;
    editingQueuedTurnId?: string | null;
    onEditQueuedTurn?: (requestId: string) => void;
    onCancelQueueEdit?: () => void;
    onSaveQueueEdit?: (requestId: string, message: string) => Promise<boolean>;
    queuePaused?: boolean;
    onResumeQueue?: () => void;
    onRetryFailedTurn?: (requestId: string) => void;
    onSteerQueuedTurn?: (requestId: string) => void;
    sttActive?: boolean;
    ttsActive?: boolean;
    onSttToggle?: () => void;
    onTtsToggle?: () => void;
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
      <button type="button" aria-pressed={sttActive} onClick={onSttToggle}>
        Dictate to composer
      </button>
      <button type="button" aria-pressed={ttsActive} onClick={onTtsToggle}>
        Voice conversation
      </button>
      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          disabled={stopping}
          aria-label={stopping ? "Stopping response" : "Stop response"}
        >
          {stopping ? "Stopping response" : "Stop response"}
        </button>
      ) : null}
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
            <>
              <button type="button" onClick={() => onEditQueuedTurn?.(turn.clientRequestId)}>
                Edit {turn.clientRequestId}
              </button>
              <button type="button" onClick={() => onSteerQueuedTurn?.(turn.clientRequestId)}>
                Steer {turn.clientRequestId}
              </button>
            </>
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
      error?: { message?: string } | null;
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
        .map((message) => message.error?.message ?? "")
        .filter(Boolean)
        .join("|")}
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
    cancelMock.mockReset();
    queueEventHandler.current = null;
    voiceRoomMock.handlers.clear();
    voiceRoomMock.on.mockClear();
    voiceRoomMock.off.mockClear();
    voiceRoomMock.startAudio.mockClear();
    voiceRoomMock.connect.mockClear();
    voiceRoomMock.disconnect.mockClear();
    voiceRoomMock.localParticipant.setMicrophoneEnabled.mockClear();
    voiceRoomMock.localParticipant.publishData.mockClear();
    voiceRoomMock.remoteParticipants.clear();

    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url.startsWith("/voice/token?")) {
        return { ok: true, json: async () => ({ token: "voice-token" }) };
      }

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

  it("keeps dictation in the composer without submitting it", async () => {
    renderChat({ activeConversationId: "conv-1" });
    await waitForSelectedConversationReady();

    fireEvent.click(screen.getByRole("button", { name: "Dictate to composer" }));
    await waitFor(() => expect(voiceRoomMock.localParticipant.publishData).toHaveBeenCalled());

    const dataHandler = voiceRoomMock.handlers.get("dataReceived");
    expect(dataHandler).toBeDefined();
    act(() => {
      dataHandler?.(
        new TextEncoder().encode(JSON.stringify({ type: "dictation-result", text: "Search this" })),
      );
    });

    await waitFor(() => {
      expect(screen.getByLabelText("DeepSpace composer draft")).toHaveValue("Search this");
    });
    expect(startMock).not.toHaveBeenCalled();
  });

  it("submits voice turns to the selected DeepSpace chat and speaks only new visible output", async () => {
    startMock.mockImplementationOnce(
      async (options: {
        onEvent: (event: { event: string; data: Record<string, unknown> }) => void;
        onFinally?: () => void;
      }) => {
        options.onEvent({ event: "start", data: { conversation_id: "conv-1" } });
        options.onEvent({ event: "tool_start", data: { tool_name: "web_search" } });
        options.onEvent({ event: "thinking", data: { text: "private reasoning" } });
        options.onEvent({ event: "tool_result", data: { output: "private tool payload" } });
        options.onEvent({ event: "delta", data: { text: "I found two useful reports." } });
        options.onEvent({ event: "done", data: {} });
        options.onFinally?.();
      },
    );

    renderChat({ activeConversationId: "conv-1" });
    await waitForSelectedConversationReady();
    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Voice conversation" }));

    await waitFor(() => {
      const modeMessages = voiceRoomMock.localParticipant.publishData.mock.calls
        .map(([bytes]) => JSON.parse(new TextDecoder().decode(bytes)))
        .filter((message) => message.type === "set-mode");
      expect(modeMessages).toContainEqual(
        expect.objectContaining({ type: "set-mode", stt: true, tts: true }),
      );
    });
    const beforeNewTurn = voiceRoomMock.localParticipant.publishData.mock.calls.map(([bytes]) =>
      JSON.parse(new TextDecoder().decode(bytes)),
    );
    expect(beforeNewTurn.some((message) => message.type === "speak-text")).toBe(false);

    const dataHandler = voiceRoomMock.handlers.get("dataReceived");
    expect(dataHandler).toBeDefined();
    act(() => {
      dataHandler?.(
        new TextEncoder().encode(
          JSON.stringify({ type: "dictation-result", text: "What is new today?" }),
        ),
      );
    });

    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(1));
    const request = startMock.mock.calls[0]?.[1] as {
      body: { message: string; conversation_id: string };
    };
    expect(request.body).toMatchObject({
      message: "What is new today?",
      conversation_id: "conv-1",
    });
    expect(screen.getByLabelText("DeepSpace composer draft")).toHaveValue("hi");

    const speechMessages = voiceRoomMock.localParticipant.publishData.mock.calls
      .map(([bytes]) => JSON.parse(new TextDecoder().decode(bytes)))
      .filter((message) => message.type === "speak-text");
    expect(speechMessages.map((message) => message.text)).toEqual([
      "I’m checking the latest sources now.",
      "I found two useful reports.",
    ]);
    expect(JSON.stringify(speechMessages)).not.toContain("private reasoning");
    expect(JSON.stringify(speechMessages)).not.toContain("private tool payload");
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

  it("stops queue and history follow-up requests when the selected conversation is gone", async () => {
    const onConversationUnavailable = vi.fn();
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/missing-conversation/messages") {
        return { ok: false, status: 404, json: async () => ({}) };
      }
      throw new Error(`Unexpected request for a missing conversation: ${url}`);
    });

    renderChat({
      activeConversationId: "missing-conversation",
      onConversationUnavailable,
    });

    await waitFor(() => {
      expect(onConversationUnavailable).toHaveBeenCalledWith("missing-conversation");
    });

    expect(
      fetchWithAuthMock.mock.calls
        .map(([url]) => url)
        .filter((url) => url.includes("missing-conversation")),
    ).toEqual(["/deepspace/chats/missing-conversation/messages"]);
  });

  it("reconciles a stopped stream if the worker never sends its terminal event", async () => {
    let cancelAttempts = 0;
    fetchWithAuthMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return { ok: true, json: async () => ({ messages: [] }) };
      }
      if (url === "/deepspace/chats/conv-1/queue") {
        return { ok: true, json: async () => [] };
      }
      if (url === "/deepspace/chats/conv-1/cancel" && init?.method === "POST") {
        cancelAttempts += 1;
        if (cancelAttempts === 1) {
          return {
            ok: false,
            status: 503,
            headers: { get: () => "0" },
            json: async () => ({ error: { message: "Temporary database issue." } }),
          };
        }
        return { ok: true, status: 204, headers: { get: () => null } };
      }
      return { ok: true, json: async () => ({}) };
    });
    renderChat({ activeConversationId: "conv-1" });
    await waitForSelectedConversationReady();
    startMock.mockImplementationOnce(
      async (options: { onEvent: (event: Record<string, unknown>) => void }) => {
        options.onEvent({
          event: "start",
          data: { message_id: "assistant-live", conversation_id: "conv-1" },
        });
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit Query" }));
    await screen.findByRole("button", { name: "Stop response" });

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", { name: "Stop response" }));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(8_000);
      });

      expect(cancelAttempts).toBe(2);
      expect(cancelMock).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not reattach in a loop after the stream endpoint returns HTTP 503", async () => {
    let historyRequests = 0;
    let submitted = false;
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        historyRequests += 1;
        return {
          ok: true,
          json: async () => ({
            messages: submitted
              ? [
                  {
                    id: "user-saved",
                    role: "user",
                    content: "hi",
                    created_at: new Date().toISOString(),
                    metadata_json: {},
                  },
                  {
                    id: "assistant-active",
                    role: "assistant",
                    content: "",
                    created_at: new Date().toISOString(),
                    metadata_json: {
                      status: "streaming",
                      runtime_active: true,
                      client_request_id: "saved-run-id",
                    },
                  },
                ]
              : [],
          }),
        };
      }
      return { ok: true, json: async () => [] };
    });
    startMock.mockImplementation(
      async (options: {
        onTransportError?: (error: { code: string; message: string }) => void;
      }) => {
        submitted = true;
        await Promise.resolve();
        options.onTransportError?.({
          code: "STREAM_HTTP_ERROR",
          message: "The service is temporarily unavailable.",
        });
      },
    );

    renderChat({ activeConversationId: "conv-1" });
    await waitForSelectedConversationReady();
    const historyRequestsBeforeSubmit = historyRequests;
    fireEvent.click(screen.getByRole("button", { name: "Set Query" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit Query" }));

    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toHaveTextContent(
        "The service is temporarily unavailable.",
      );
    });
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 25));
    });

    expect(startMock).toHaveBeenCalledTimes(1);
    expect(historyRequests).toBe(historyRequestsBeforeSubmit);
    expect(screen.queryByRole("button", { name: "Stop response" })).not.toBeInTheDocument();
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
    await waitForSelectedConversationReady();
    const historyLoadsBeforeSwitch = historyLoads;
    fireEvent.click(screen.getByRole("button", { name: "Previous response version" }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/deepspace/chats/conv-1/messages/assistant-versioned/versions/version-1/activate",
        { method: "PATCH" },
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("deepspace-thread")).toHaveTextContent(
        "assistant:Saved response version 2.",
      );
      expect(historyLoads).toBeGreaterThan(historyLoadsBeforeSwitch);
    });
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

  it("waits for a worker claim before reconnecting after queue resume", async () => {
    let queueIsPaused = true;
    let queueIsClaimed = false;
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
            active_request_id: !queueIsPaused && queueIsClaimed ? "queued-next" : null,
          }),
        };
      }
      if (url === "/deepspace/chats/conv-1/queue/resume" && init?.method === "POST") {
        queueIsPaused = false;
        return {
          ok: true,
          json: async () => ({ paused: false, active_request_id: null }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });
    fireEvent.click(await screen.findByRole("button", { name: "Resume queue" }));

    await waitFor(() => {
      expect(
        fetchWithAuthMock.mock.calls.some(
          ([url]) => url === "/deepspace/chats/conv-1/queue/resume",
        ),
      ).toBe(true);
    });
    expect(startMock).not.toHaveBeenCalled();

    queueIsClaimed = true;
    await act(async () => {
      queueEventHandler.current?.({ data: { conversation_id: "conv-1" } });
      await Promise.resolve();
    });

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

  it("keeps a retry queued instead of reconnecting before a worker claims it", async () => {
    fetchWithAuthMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return { ok: true, json: async () => ({ messages: [] }) };
      }
      if (url === "/deepspace/chats/conv-1/queue" && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({ client_request_id: "retry-attempt" }),
        };
      }
      if (url === "/deepspace/chats/conv-1/queue") {
        return {
          ok: true,
          json: async () => [
            {
              client_request_id: "failed-attempt",
              prompt: "Original saved prompt",
              priority: 0,
              sequence: 1,
              status: "failed",
              error: "Provider temporarily unavailable",
            },
            {
              client_request_id: "retry-attempt",
              prompt: "Original saved prompt",
              priority: 1,
              sequence: 2,
              status: "queued",
            },
          ],
        };
      }
      if (url === "/deepspace/chats/conv-1/queue/state") {
        return { ok: true, json: async () => ({ paused: false, active_request_id: null }) };
      }
      if (url === "/deepspace/chats/conv-1/queue/failed-attempt/retry") {
        return {
          ok: true,
          json: async () => ({ client_request_id: "retry-attempt", status: "queued" }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });
    fireEvent.click(await screen.findByRole("button", { name: "Retry failed-attempt" }));

    await waitFor(() => {
      expect(screen.getByTestId("composer-queue")).toHaveTextContent("Original saved prompt");
    });
    expect(startMock).not.toHaveBeenCalled();
  });

  it("steers a pending turn without reconnecting until its worker claims it", async () => {
    let activeRequestId: string | null = "active-turn";
    let workerClaimed = false;
    const cancellationBodies: Array<Record<string, unknown>> = [];
    fetchWithAuthMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/deepspace/chats/conv-1/messages") {
        return { ok: true, json: async () => ({ messages: [] }) };
      }
      if (url === "/deepspace/chats/conv-1/queue") {
        return {
          ok: true,
          json: async () => [
            {
              client_request_id: "pending-turn",
              prompt: "Prioritize this pending prompt",
              priority: 0,
              sequence: 2,
              status: "queued",
            },
          ],
        };
      }
      if (url === "/deepspace/chats/conv-1/queue/state") {
        return {
          ok: true,
          json: async () => ({
            paused: false,
            active_request_id: workerClaimed ? "pending-turn" : activeRequestId,
          }),
        };
      }
      if (url === "/deepspace/chats/conv-1/queue/pending-turn/steer") {
        return {
          ok: true,
          json: async () => ({
            client_request_id: "pending-turn",
            prompt: "Prioritize this pending prompt",
            priority: 1,
            sequence: 2,
            status: "queued",
          }),
        };
      }
      if (url === "/deepspace/chats/conv-1/cancel") {
        cancellationBodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        activeRequestId = null;
        return {
          ok: true,
          status: 204,
          headers: { get: () => "1" },
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    renderChat({ activeConversationId: "conv-1" });
    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(1));
    expect(startMock.mock.calls[0]?.[1]).toMatchObject({
      body: expect.objectContaining({ client_request_id: "active-turn", reconnect: true }),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Steer pending-turn" }));
    await waitFor(() => expect(cancellationBodies).toEqual([{ client_request_id: "active-turn" }]));
    expect(startMock).toHaveBeenCalledTimes(1);

    workerClaimed = true;
    await act(async () => {
      queueEventHandler.current?.({ data: { conversation_id: "conv-1" } });
      await Promise.resolve();
    });
    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(2));
    expect(startMock.mock.calls[1]?.[1]).toMatchObject({
      body: expect.objectContaining({ client_request_id: "pending-turn", reconnect: true }),
    });
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
