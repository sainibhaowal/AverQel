import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  compactQueuedEvents,
  useDeepSpaceStream,
} from "@/app/dashboard/deepspace/_hooks/useDeepSpaceStream";
import type { DeepSpaceStreamEvent } from "@/app/dashboard/deepspace/_lib/deepspace-stream";
import { connectDeepSpaceWebSocketStream } from "@/app/dashboard/deepspace/websocketIntegration";

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readonly sentMessages: string[] = [];
  readonly listeners = new Map<string, Set<(event: Event | MessageEvent) => void>>();

  readyState = 0;
  closeCode: number | null = null;
  closeReason = "";

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: (event: Event | MessageEvent) => void) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)?.add(listener);
  }

  removeEventListener(type: string, listener: (event: Event | MessageEvent) => void) {
    this.listeners.get(type)?.delete(listener);
  }

  send(payload: string) {
    this.sentMessages.push(payload);
  }

  close(code = 1000, reason = "") {
    this.closeCode = code;
    this.closeReason = reason;
    if (this.readyState === 3) {
      return;
    }
    this.readyState = 3;
    this.dispatch("close", new Event("close"));
  }

  open() {
    this.readyState = 1;
    this.dispatch("open", new Event("open"));
  }

  emitMessage(data: string) {
    this.dispatch("message", new MessageEvent("message", { data }));
  }

  emitError() {
    this.dispatch("error", new Event("error"));
  }

  private dispatch(type: string, event: Event | MessageEvent) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

function setWebSocketMock() {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
}

describe("DeepSpace websocket streaming", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem("averqel_token", "token-123");
    window.localStorage.setItem("averqel_tenant_id", "tenant-42");
    window.requestAnimationFrame = vi.fn((callback: FrameRequestCallback) => {
      callback(16);
      return 1;
    });
    window.cancelAnimationFrame = vi.fn();
    setWebSocketMock();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("keeps queued events intact so streamed tokens are not compacted away", () => {
    const events: DeepSpaceStreamEvent[] = [
      { event: "delta", data: { text: "Hello" } },
      { event: "delta", data: { text: " world" } },
      { event: "thinking", data: { text: "Plan A" } },
      { event: "thinking", data: { text: " -> Plan B" } },
    ];

    expect(compactQueuedEvents(events)).toEqual(events);
  });

  it("opens a websocket, sends the request payload, and forwards every streamed frame", async () => {
    const onEvents = vi.fn();
    const onTransportError = vi.fn();
    const onOpen = vi.fn();
    const onClose = vi.fn();

    const handle = connectDeepSpaceWebSocketStream({
      endpoint: "/deepspace/chats/stream",
      body: { query: "quantum" },
      onEvents,
      onTransportError,
      onOpen,
      onClose,
    });

    expect(handle).not.toBeNull();
    expect(MockWebSocket.instances).toHaveLength(1);

    const socket = MockWebSocket.instances[0]!;
    expect(socket.url).toContain("/api/v1/deepspace/chats/ws");
    expect(socket.url).toContain("token=token-123");
    expect(socket.url).toContain("tenant_id=tenant-42");

    socket.open();
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(socket.sentMessages[0]).toBe(
      JSON.stringify({
        endpoint: "/deepspace/chats/stream",
        method: "POST",
        body: { query: "quantum" },
      }),
    );

    socket.emitMessage('event: delta\ndata: {"text":"Hel"}\n\n');
    socket.emitMessage('event: delta\ndata: {"text":"lo"}\n\n');
    socket.emitMessage('event: thinking\ndata: {"text":"Working"}\n\n');
    socket.emitMessage('event: done\ndata: {"completed":true}\n\n');

    await handle?.closed;

    expect(onEvents).toHaveBeenNthCalledWith(1, [{ event: "delta", data: { text: "Hel" } }]);
    expect(onEvents).toHaveBeenNthCalledWith(2, [{ event: "delta", data: { text: "lo" } }]);
    expect(onEvents).toHaveBeenNthCalledWith(3, [{ event: "thinking", data: { text: "Working" } }]);
    expect(onTransportError).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("streams websocket events through the hook and settles without a fake cancel", async () => {
    const onEvent = vi.fn<(event: DeepSpaceStreamEvent) => void>();
    const onTransportError = vi.fn();
    const onFinally = vi.fn();
    const onUserCancel = vi.fn();

    const { result } = renderHook(() =>
      useDeepSpaceStream({
        onEvent,
        onTransportError,
        onFinally,
        onUserCancel,
      }),
    );

    let startPromise: Promise<void> | undefined;

    await act(async () => {
      startPromise = result.current.start({
        body: { query: "stream tokens" },
      });
      await Promise.resolve();
    });

    const socket = MockWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket?.open();
    socket?.emitMessage('event: delta\ndata: {"text":"One"}\n\n');
    socket?.emitMessage('event: delta\ndata: {"text":" two"}\n\n');
    socket?.emitMessage('event: done\ndata: {"completed":true}\n\n');

    await act(async () => {
      await startPromise;
    });

    expect(onEvent).toHaveBeenNthCalledWith(1, { event: "delta", data: { text: "One" } });
    expect(onEvent).toHaveBeenNthCalledWith(2, { event: "delta", data: { text: " two" } });
    expect(onTransportError).not.toHaveBeenCalled();
    expect(onFinally).toHaveBeenCalledTimes(1);
    expect(onUserCancel).not.toHaveBeenCalled();
  });

  it("cancels a live websocket stream without reporting a transport error", async () => {
    const onEvent = vi.fn();
    const onTransportError = vi.fn();
    const onUserCancel = vi.fn();

    const { result } = renderHook(() =>
      useDeepSpaceStream({
        onEvent,
        onTransportError,
        onUserCancel,
      }),
    );

    await act(async () => {
      void result.current.start({
        body: { query: "cancel me" },
      });
      await Promise.resolve();
    });

    const socket = MockWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket?.open();

    await act(async () => {
      result.current.cancel();
    });

    expect(onUserCancel).toHaveBeenCalledTimes(1);
    expect(onTransportError).not.toHaveBeenCalled();
    expect(socket?.closeCode).toBe(1000);
  });
});
