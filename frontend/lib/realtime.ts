"use client";

import { useEffect, useRef, useState } from "react";
import { fetchWithAuth, getApiBaseUrl } from "@/lib/api";

type RealtimePayload = {
  event_id?: string;
  type: string;
  resource: string;
  data?: Record<string, unknown>;
  occurred_at?: string;
};

export type RealtimeConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected";

function realtimeUrl(ticket: string): URL | null {
  if (typeof window === "undefined" || typeof WebSocket === "undefined") return null;
  const url = new URL(`${getApiBaseUrl().replace(/\/+$/, "")}/realtime/ws`, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("ticket", ticket);
  return url;
}

export function useRealtimeEvents(
  onEvent: (event: RealtimePayload) => void,
  resources: string[] = [],
) {
  const [connectionState, setConnectionState] = useState<RealtimeConnectionState>("disconnected");
  const callbackRef = useRef(onEvent);
  const resourcesRef = useRef(resources);

  useEffect(() => {
    callbackRef.current = onEvent;
    resourcesRef.current = resources;
  }, [onEvent, resources]);

  const resourceKey = resources.join("|");

  useEffect(() => {
    // Browser E2E uses deterministic HTTP fixtures and a closed API sink. Do
    // not start a reconnect loop for an optional realtime transport that is
    // intentionally absent from that isolated environment.
    if (process.env.NEXT_PUBLIC_E2E_DISABLE_REALTIME === "1") {
      return;
    }
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let stopped = false;
    let retryDelay = 500;
    let storedUserId = "unknown";
    try {
      const storedUser = JSON.parse(window.localStorage.getItem("averqel_user") ?? "null") as {
        id?: unknown;
      } | null;
      if (typeof storedUser?.id === "string" && storedUser.id) storedUserId = storedUser.id;
    } catch {
      // A malformed cached profile must not prevent the realtime connection.
    }
    const cursorKey = `averqel_realtime_cursor:${window.localStorage.getItem("averqel_tenant_id") ?? "unknown"}:${storedUserId}`;

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer !== null) return;
      setConnectionState("reconnecting");
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 10_000);
    };

    const connect = async () => {
      if (stopped) return;
      if (!window.localStorage.getItem("averqel_token")) {
        setConnectionState("disconnected");
        return;
      }
      setConnectionState(retryDelay > 500 ? "reconnecting" : "connecting");

      try {
        // fetchWithAuth refreshes an expired/near-expiry access token before it
        // mints the one-use ticket, so the browser never retries a stale JWT.
        const ticketResponse = await fetchWithAuth("/realtime/ticket", {
          method: "POST",
          silentTimeout: true,
        });
        if (!ticketResponse.ok) throw new Error("Realtime ticket request failed.");
        const ticketPayload = (await ticketResponse.json()) as { ticket?: unknown };
        if (stopped) return;
        if (typeof ticketPayload.ticket !== "string") {
          throw new Error("Realtime ticket response was invalid.");
        }

        const url = realtimeUrl(ticketPayload.ticket);
        if (!url) {
          setConnectionState("disconnected");
          return;
        }
        const cursor = window.localStorage.getItem(cursorKey);
        if (cursor) url.searchParams.set("last_event_id", cursor);
        const currentSocket = new WebSocket(url.toString());
        socket = currentSocket;
        currentSocket.onopen = () => {
          retryDelay = 500;
          setConnectionState("connected");
        };
        currentSocket.onmessage = (message) => {
          try {
            const envelope = JSON.parse(String(message.data)) as {
              event?: string;
              cursor?: string;
              payload?: RealtimePayload;
            };
            if (envelope.cursor) window.localStorage.setItem(cursorKey, envelope.cursor);
            if (
              envelope.event === "realtime" &&
              envelope.payload &&
              (!resourcesRef.current.length ||
                resourcesRef.current.includes(envelope.payload.resource))
            ) {
              callbackRef.current(envelope.payload);
            }
          } catch {
            // Ignore malformed frames; the next snapshot remains authoritative.
          }
        };
        currentSocket.onclose = () => {
          if (socket === currentSocket) socket = null;
          if (stopped) {
            setConnectionState("disconnected");
            return;
          }
          scheduleReconnect();
        };
        currentSocket.onerror = () => currentSocket.close();
      } catch {
        // Realtime is an optional invalidation hint; REST snapshots remain
        // authoritative while auth or the transport is recovering.
        scheduleReconnect();
      }
    };

    void connect();
    return () => {
      stopped = true;
      setConnectionState("disconnected");
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [resourceKey]);

  return connectionState;
}
