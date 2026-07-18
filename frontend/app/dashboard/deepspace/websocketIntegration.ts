"use client";

import { getApiBaseUrl } from "@/lib/api";

import { parseSseFrames, type DeepSpaceStreamEvent } from "./_lib/deepspace-stream";

export interface DeepSpaceWebSocketStreamOptions {
  endpoint: string;
  body: Record<string, unknown>;
  onEvents: (events: DeepSpaceStreamEvent[]) => void;
  onTransportError: (error: { code: string; message: string }) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

export interface DeepSpaceWebSocketStreamHandle {
  socket: WebSocket;
  closed: Promise<void>;
  close: () => void;
}

function getStoredAuthTokens() {
  if (typeof window === "undefined") {
    return { token: null, tenantId: null };
  }
  return {
    token: window.localStorage.getItem("averqel_token"),
    tenantId: window.localStorage.getItem("averqel_tenant_id"),
  };
}

function buildWebSocketUrl(): string | null {
  if (typeof window === "undefined") return null;

  const baseUrl = getApiBaseUrl().replace(/\/+$/, "");
  try {
    const url = new URL(`${baseUrl}/deepspace/chats/ws`, window.location.origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const { token, tenantId } = getStoredAuthTokens();
    if (token) {
      url.searchParams.set("token", token);
    }
    if (tenantId) {
      url.searchParams.set("tenant_id", tenantId);
    }
    return url.toString();
  } catch {
    return null;
  }
}

export function connectDeepSpaceWebSocketStream(
  options: DeepSpaceWebSocketStreamOptions,
): DeepSpaceWebSocketStreamHandle | null {
  if (typeof window === "undefined" || typeof window.WebSocket === "undefined") {
    options.onTransportError({
      code: "WEBSOCKET_UNAVAILABLE",
      message: "WebSocket is unavailable in this environment.",
    });
    return null;
  }

  const url = buildWebSocketUrl();
  if (!url) {
    options.onTransportError({
      code: "WEBSOCKET_URL_ERROR",
      message: "Unable to resolve the DeepSpace WebSocket URL.",
    });
    return null;
  }

  const socket = new WebSocket(url);
  let completed = false;
  let settled = false;
  let resolveClosed: (() => void) | null = null;
  const closed = new Promise<void>((resolve) => {
    resolveClosed = resolve;
  });

  const finish = () => {
    if (settled) return;
    settled = true;
    resolveClosed?.();
  };

  socket.addEventListener("open", () => {
    options.onOpen?.();
    socket.send(
      JSON.stringify({
        endpoint: options.endpoint,
        method: "POST",
        body: options.body,
      }),
    );
  });

  socket.addEventListener("message", (message) => {
    const raw = String(message.data ?? "");
    if (!raw.trim()) return;

    try {
      const parsed = parseSseFrames(raw);
      if (parsed.events.length === 0) return;
      options.onEvents(parsed.events);
      if (parsed.events.some((event) => event.event === "done" || event.event === "error")) {
        completed = true;
        socket.close(1000, "DeepSpace stream completed");
      }
    } catch (error) {
      options.onTransportError({
        code: "WEBSOCKET_PARSE_ERROR",
        message: error instanceof Error ? error.message : "Failed to parse WebSocket payload.",
      });
      socket.close(1011, "Parse error");
    }
  });

  socket.addEventListener("error", () => {
    options.onTransportError({
      code: "WEBSOCKET_ERROR",
      message: "Real-time WebSocket connection failed.",
    });
  });

  socket.addEventListener("close", () => {
    options.onClose?.();
    if (!completed) {
      options.onTransportError({
        code: "WEBSOCKET_CLOSED",
        message: "The DeepSpace WebSocket connection closed unexpectedly.",
      });
    }
    finish();
  });

  return {
    socket,
    closed,
    close: () => socket.close(1000, "Client closed"),
  };
}

export function canUseDeepSpaceWebSocket(): boolean {
  return typeof window !== "undefined" && typeof window.WebSocket !== "undefined";
}
