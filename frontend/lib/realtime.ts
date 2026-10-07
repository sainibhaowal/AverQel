"use client";

import { useEffect, useRef, useState } from "react";
import { getApiBaseUrl } from "@/lib/api";

type RealtimePayload = {
  event_id?: string;
  type: string;
  resource: string;
  data?: Record<string, unknown>;
  occurred_at?: string;
};

export type RealtimeConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected";

function realtimeUrl(): URL | null {
  if (typeof window === "undefined" || typeof WebSocket === "undefined") return null;
  const token = window.localStorage.getItem("averqel_token");
  if (!token) return null;
  const tenantId = window.localStorage.getItem("averqel_tenant_id");
  const url = new URL(`${getApiBaseUrl().replace(/\/+$/, "")}/realtime/ws`, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", token);
  if (tenantId) url.searchParams.set("tenant_id", tenantId);
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

    const connect = () => {
      if (stopped) return;
      const url = realtimeUrl();
      if (!url) {
        setConnectionState("disconnected");
        return;
      }
      setConnectionState(retryDelay > 500 ? "reconnecting" : "connecting");
      const cursor = window.localStorage.getItem(cursorKey);
      if (cursor) url.searchParams.set("last_event_id", cursor);
      socket = new WebSocket(url.toString());
      socket.onopen = () => {
        retryDelay = 500;
        setConnectionState("connected");
      };
      socket.onmessage = (message) => {
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
      socket.onclose = () => {
        socket = null;
        if (stopped) {
          setConnectionState("disconnected");
          return;
        }
        setConnectionState("reconnecting");
        reconnectTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 10_000);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      stopped = true;
      setConnectionState("disconnected");
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [resourceKey]);

  return connectionState;
}
