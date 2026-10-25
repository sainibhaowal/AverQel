import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchWithAuth, getApiBaseUrl } from "@/lib/api";
import { useRealtimeEvents } from "@/lib/realtime";

vi.mock("@/lib/api", () => ({
  fetchWithAuth: vi.fn(),
  getApiBaseUrl: vi.fn(() => "/api/v1"),
}));

const fetchWithAuthMock = vi.mocked(fetchWithAuth);
const getApiBaseUrlMock = vi.mocked(getApiBaseUrl);

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;

  constructor(readonly url: string) {
    MockWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.();
  }
}

function ticketResponse(ticket: string): Response {
  return new Response(JSON.stringify({ ticket, expires_in_seconds: 60 }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("useRealtimeEvents", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem("averqel_token", "expired-access-token");
    fetchWithAuthMock.mockReset().mockResolvedValue(ticketResponse("one-use-ticket"));
    getApiBaseUrlMock.mockReturnValue("https://localhost/api/v1");
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("refreshes through the authenticated API path and keeps JWTs out of the socket URL", async () => {
    const onEvent = vi.fn();
    const { unmount } = renderHook(() => useRealtimeEvents(onEvent, ["deepspace"]));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));

    expect(fetchWithAuthMock).toHaveBeenCalledWith("/realtime/ticket", {
      method: "POST",
      silentTimeout: true,
    });
    const socketUrl = new URL(MockWebSocket.instances[0]!.url);
    expect(socketUrl.protocol).toBe("wss:");
    expect(socketUrl.pathname).toBe("/api/v1/realtime/ws");
    expect(socketUrl.searchParams.get("ticket")).toBe("one-use-ticket");
    expect(socketUrl.searchParams.has("token")).toBe(false);
    expect(MockWebSocket.instances[0]!.url).not.toContain("expired-access-token");

    unmount();
  });

  it("delivers only subscribed events from the authenticated stream", async () => {
    const onEvent = vi.fn();
    const { unmount } = renderHook(() => useRealtimeEvents(onEvent, ["deepspace"]));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    const socket = MockWebSocket.instances[0]!;

    act(() => {
      socket.onmessage?.({
        data: JSON.stringify({
          event: "realtime",
          cursor: "1-0",
          payload: { type: "chat.updated", resource: "deepspace", data: {} },
        }),
      });
      socket.onmessage?.({
        data: JSON.stringify({
          event: "realtime",
          cursor: "2-0",
          payload: { type: "document.updated", resource: "documents", data: {} },
        }),
      });
    });

    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith({
      type: "chat.updated",
      resource: "deepspace",
      data: {},
    });
    expect(window.localStorage.getItem("averqel_realtime_cursor:unknown:unknown")).toBe("2-0");

    unmount();
  });

  it("requests a fresh one-use ticket after a dropped socket", async () => {
    fetchWithAuthMock
      .mockReset()
      .mockResolvedValueOnce(ticketResponse("first-ticket"))
      .mockResolvedValueOnce(ticketResponse("second-ticket"));
    const { unmount } = renderHook(() => useRealtimeEvents(vi.fn(), ["deepspace"]));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    const firstSocket = MockWebSocket.instances[0]!;
    vi.useFakeTimers();

    await act(async () => {
      firstSocket.onclose?.();
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(fetchWithAuthMock).toHaveBeenCalledTimes(2);
    expect(MockWebSocket.instances).toHaveLength(2);
    expect(new URL(MockWebSocket.instances[1]!.url).searchParams.get("ticket")).toBe(
      "second-ticket",
    );

    unmount();
  });
});
