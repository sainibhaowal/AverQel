import { act, renderHook } from "@testing-library/react";
import { vi } from "vitest";

import { useQueryStream } from "@/app/dashboard/query/_hooks/useQueryStream";
import type { QueryStreamEvent } from "@/app/dashboard/query/_lib/stream-protocol";
import { fetchWithAuth } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  fetchWithAuth: vi.fn(),
}));

const fetchWithAuthMock = vi.mocked(fetchWithAuth);

function createStreamResponse(chunks: Array<string | Error>): Response {
  let index = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close();
        return;
      }

      const nextChunk = chunks[index++];
      if (nextChunk instanceof Error) {
        controller.error(nextChunk);
        return;
      }

      controller.enqueue(new TextEncoder().encode(nextChunk));
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
    },
  });
}

describe("useQueryStream", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("retries once when the browser reports ERR_NETWORK_CHANGED before any event arrives", async () => {
    const onEvent = vi.fn<(event: QueryStreamEvent) => void>();
    const onTransportError = vi.fn();
    const onFinally = vi.fn();

    fetchWithAuthMock
      .mockRejectedValueOnce(new Error("net::ERR_NETWORK_CHANGED"))
      .mockResolvedValueOnce(createStreamResponse(['event: done\ndata: {"completed":true}\n\n']));

    const { result } = renderHook(() =>
      useQueryStream({
        onEvent,
        onTransportError,
        onFinally,
      }),
    );

    const startPromise = result.current.start({
      body: { query: "hello" },
    });

    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    await act(async () => {
      await startPromise;
    });

    expect(fetchWithAuthMock).toHaveBeenCalledTimes(2);
    expect(onEvent).toHaveBeenCalledWith({
      event: "done",
      data: { completed: true },
    });
    expect(onTransportError).not.toHaveBeenCalled();
    expect(onFinally).toHaveBeenCalledTimes(1);
  });

  it("does not retry after the stream has already emitted an event", async () => {
    const onEvent = vi.fn<(event: QueryStreamEvent) => void>();
    const onTransportError = vi.fn();

    fetchWithAuthMock.mockResolvedValueOnce(
      createStreamResponse([
        'event: start\ndata: {"message_id":"m1","conversation_id":"c1","started_at":"2026-04-10T00:00:00Z"}\n\n',
        new Error("net::ERR_NETWORK_CHANGED"),
      ]),
    );

    const { result } = renderHook(() =>
      useQueryStream({
        onEvent,
        onTransportError,
      }),
    );

    await act(async () => {
      await result.current.start({
        body: { query: "hello" },
      });
    });

    expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith({
      event: "start",
      data: {
        message_id: "m1",
        conversation_id: "c1",
        started_at: "2026-04-10T00:00:00Z",
      },
    });
    expect(onTransportError).toHaveBeenCalledTimes(1);
    expect(onTransportError).toHaveBeenCalledWith({
      code: "STREAM_TRANSPORT_ERROR",
      message: "net::ERR_NETWORK_CHANGED",
    });
  });
});
