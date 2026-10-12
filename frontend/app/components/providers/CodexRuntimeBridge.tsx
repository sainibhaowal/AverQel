"use client";

import { useEffect } from "react";

import { fetchWithAuth, getApiBaseUrl } from "@/lib/api";

type CodexRequestPacket = {
  event: "codex_infer" | "codex_cancel";
  id: string;
  params?: {
    account_id?: string;
    request?: Record<string, unknown>;
  };
};

function tokenIdentity(token: string): string | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const binary = window.atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const claims = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
    if (typeof claims.sub !== "string" || typeof claims.tenant_id !== "string") return null;
    return `${claims.tenant_id}:${claims.sub}`;
  } catch {
    return null;
  }
}

function runtimeSocketUrl(ticket: string): URL | null {
  if (typeof window === "undefined" || typeof WebSocket === "undefined") return null;
  const url = new URL(
    `${getApiBaseUrl().replace(/\/+$/, "")}/deepspace/codex-runtime/ws`,
    window.location.origin,
  );
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("ticket", ticket);
  return url;
}

export default function CodexRuntimeBridge() {
  useEffect(() => {
    const desktop = window.electron;
    if (!desktop?.isElectron || !desktop.codex) return;

    let stopped = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let heartbeatTimer: number | null = null;
    let retryDelay = 500;
    const activeStreams = new Set<string>();
    const cancelledBeforeStart = new Set<string>();

    const sendFrame = (streamId: string, kind: "event" | "error" | "closed", data?: unknown) => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(
        JSON.stringify({
          event: "codex_stream_frame",
          id: streamId,
          kind,
          ...(data === undefined ? {} : { data }),
        }),
      );
    };

    const stopStreams = () => {
      for (const streamId of activeStreams) void desktop.codex.cancelStream(streamId);
      activeStreams.clear();
      cancelledBeforeStart.clear();
    };

    const unsubscribe = desktop.codex.onStreamEvent((frame) => {
      if (!frame || typeof frame.streamId !== "string") return;
      if (frame.kind === "event" && frame.event) {
        sendFrame(frame.streamId, "event", frame.event);
      } else if (frame.kind === "error") {
        sendFrame(frame.streamId, "error", {
          message: frame.message || "Codex request failed.",
          ...(Number.isInteger(frame.httpStatus) ? { http_status: frame.httpStatus } : {}),
          ...(typeof frame.code === "string" ? { code: frame.code } : {}),
          ...(typeof frame.param === "string" ? { param: frame.param } : {}),
          ...(typeof frame.requestId === "string" ? { request_id: frame.requestId } : {}),
        });
      } else if (frame.kind === "closed") {
        sendFrame(frame.streamId, "closed");
        activeStreams.delete(frame.streamId);
        cancelledBeforeStart.delete(frame.streamId);
      }
    });

    const handleRequest = async (packet: CodexRequestPacket) => {
      if (packet.event === "codex_cancel") {
        if (!activeStreams.has(packet.id)) cancelledBeforeStart.add(packet.id);
        void desktop.codex.cancelStream(packet.id);
        return;
      }
      const accountId = packet.params?.account_id;
      const request = packet.params?.request;
      if (
        typeof packet.id !== "string" ||
        !/^[0-9a-f-]{36}$/i.test(packet.id) ||
        typeof accountId !== "string" ||
        !request ||
        typeof request !== "object" ||
        Array.isArray(request)
      ) {
        sendFrame(packet.id, "error", { message: "The Codex runtime request is invalid." });
        sendFrame(packet.id, "closed");
        return;
      }
      if (activeStreams.has(packet.id)) return;
      activeStreams.add(packet.id);
      try {
        await desktop.codex.startStream({
          streamId: packet.id,
          accountId,
          request,
        });
        if (cancelledBeforeStart.has(packet.id)) void desktop.codex.cancelStream(packet.id);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Codex request could not start.";
        sendFrame(packet.id, "error", { message });
        sendFrame(packet.id, "closed");
        activeStreams.delete(packet.id);
      }
    };

    const connect = () => {
      if (stopped) return;
      const initialToken = window.localStorage.getItem("averqel_token");
      if (!initialToken) {
        retryTimer = window.setTimeout(connect, 2_000);
        return;
      }
      void (async () => {
        try {
          const ticketResponse = await fetchWithAuth("/deepspace/codex-runtime/ticket", {
            method: "POST",
            silentTimeout: true,
          });
          if (!ticketResponse.ok) throw new Error("Desktop runtime ticket could not be created.");
          const ticketPayload = (await ticketResponse.json()) as { ticket?: unknown };
          if (typeof ticketPayload.ticket !== "string") {
            throw new Error("Desktop runtime ticket response was invalid.");
          }
          const sessionToken = window.localStorage.getItem("averqel_token");
          if (stopped) return;
          if (!sessionToken) {
            retryTimer = window.setTimeout(connect, 2_000);
            return;
          }
          const sessionIdentity = tokenIdentity(sessionToken);
          if (!sessionIdentity) throw new Error("The AverQel session identity is invalid.");
          const url = runtimeSocketUrl(ticketPayload.ticket);
          if (!url) return;
          socket = new WebSocket(url.toString());
          const currentSocket = socket;
          currentSocket.onopen = () => {
            retryDelay = 500;
            heartbeatTimer = window.setInterval(() => {
              const currentToken = window.localStorage.getItem("averqel_token");
              if (!currentToken || tokenIdentity(currentToken) !== sessionIdentity) {
                currentSocket.close(4001, "Authentication changed");
                return;
              }
              if (currentSocket.readyState === WebSocket.OPEN) {
                currentSocket.send(JSON.stringify({ event: "ping" }));
              }
            }, 10_000);
          };
          currentSocket.onmessage = (message) => {
            let packet: unknown;
            try {
              packet = JSON.parse(String(message.data));
            } catch {
              return;
            }
            if (!packet || typeof packet !== "object") return;
            const data = packet as Record<string, unknown>;
            if (
              data.event === "codex_infer" &&
              typeof data.id === "string" &&
              data.params &&
              typeof data.params === "object"
            ) {
              void handleRequest(data as CodexRequestPacket);
            } else if (data.event === "codex_cancel" && typeof data.id === "string") {
              void handleRequest(data as CodexRequestPacket);
            }
          };
          currentSocket.onclose = () => {
            if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
            heartbeatTimer = null;
            if (socket === currentSocket) socket = null;
            stopStreams();
            if (stopped) return;
            retryTimer = window.setTimeout(connect, retryDelay);
            retryDelay = Math.min(retryDelay * 2, 10_000);
          };
          currentSocket.onerror = () => currentSocket.close();
        } catch {
          if (stopped) return;
          retryTimer = window.setTimeout(connect, retryDelay);
          retryDelay = Math.min(retryDelay * 2, 10_000);
        }
      })();
    };

    connect();
    return () => {
      stopped = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
      unsubscribe();
      stopStreams();
      socket?.close(1000, "Dashboard closed");
    };
  }, []);

  return null;
}
