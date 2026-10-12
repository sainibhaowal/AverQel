import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { fetchWithAuth } from "@/lib/api";
import { useDeepSpaceStream } from "../app/dashboard/deepspace/_hooks/useDeepSpaceStream";

vi.mock("@/lib/api", () => ({
  fetchWithAuth: vi.fn(),
}));

const fetchWithAuthMock = vi.mocked(fetchWithAuth);

function responseFor(body: string): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(body));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

describe("useDeepSpaceStream", () => {
  it("reports an incomplete successful HTTP stream instead of silently finishing", async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      responseFor('event: start\ndata: {"message_id":"m1"}\n\n'),
    );
    const onEvent = vi.fn();
    const onTransportError = vi.fn();

    const { result } = renderHook(() => useDeepSpaceStream({ onEvent, onTransportError }));

    await act(async () => {
      await result.current.start({ body: { message: "hello" } });
    });

    expect(onTransportError).toHaveBeenCalledWith({
      code: "STREAM_INCOMPLETE",
      message: "The chat provider closed the stream before completing the response.",
    });
  });

  it("accepts a terminal done event without reporting a transport failure", async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      responseFor('event: done\ndata: {"status":"ready"}\n\n'),
    );
    const onEvent = vi.fn();
    const onTransportError = vi.fn();

    const { result } = renderHook(() => useDeepSpaceStream({ onEvent, onTransportError }));

    await act(async () => {
      await result.current.start({ body: { message: "hello" } });
    });

    expect(onEvent).toHaveBeenCalledWith({
      event: "done",
      data: { status: "ready" },
    });
    expect(onTransportError).not.toHaveBeenCalled();
  });

  it("detaches a prior reader without cancelling or finishing the durable run", async () => {
    let signal: AbortSignal | null = null;
    fetchWithAuthMock.mockImplementationOnce(async (_endpoint, options) => {
      signal = options?.signal as AbortSignal;
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode('event: start\ndata: {"message_id":"m1"}\n\n'),
          );
          signal?.addEventListener(
            "abort",
            () => controller.error(new DOMException("The request was aborted", "AbortError")),
            { once: true },
          );
        },
      });
      return new Response(body, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    });
    fetchWithAuthMock.mockResolvedValueOnce(
      responseFor('event: done\ndata: {"status":"ready"}\n\n'),
    );
    const onUserCancel = vi.fn();
    const onFinally = vi.fn();
    const { result } = renderHook(() =>
      useDeepSpaceStream({
        onEvent: vi.fn(),
        onTransportError: vi.fn(),
        onUserCancel,
        onFinally,
      }),
    );

    let priorRun: Promise<void> | undefined;
    act(() => {
      priorRun = result.current.start({ body: { conversation_id: "conv-1" } });
    });
    await waitFor(() => expect(signal).toBeInstanceOf(AbortSignal));
    act(() => result.current.detach());
    await act(async () => priorRun);

    expect(onUserCancel).not.toHaveBeenCalled();
    expect(onFinally).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.start({ body: { conversation_id: "conv-2" } });
    });
    expect(onFinally).toHaveBeenCalledTimes(1);
  });
});
