import { act, renderHook } from "@testing-library/react";
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

    const { result } = renderHook(() =>
      useDeepSpaceStream({ onEvent, onTransportError }),
    );

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

    const { result } = renderHook(() =>
      useDeepSpaceStream({ onEvent, onTransportError }),
    );

    await act(async () => {
      await result.current.start({ body: { message: "hello" } });
    });

    expect(onEvent).toHaveBeenCalledWith({
      event: "done",
      data: { status: "ready" },
    });
    expect(onTransportError).not.toHaveBeenCalled();
  });
});
