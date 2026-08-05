"use client";

import { useCallback, useRef } from "react";

import { fetchWithAuth } from "@/lib/api";
import {
  isRetryableStreamStatus,
  isRetryableStreamTransportError,
  normalizeStreamTransportMessage,
} from "@/app/lib/streaming/sseTransport";

import { parseSseFrames, type DeepSpaceStreamEvent } from "../_lib/deepspace-stream";

interface StartStreamArgs {
  endpoint?: string;
  body: Record<string, unknown>;
}

interface UseDeepSpaceStreamOptions {
  onEvent: (event: DeepSpaceStreamEvent) => void;
  onEvents?: (events: DeepSpaceStreamEvent[]) => void;
  onTransportError: (error: { code: string; message: string }) => void;
  onFinally?: () => void;
  onUserCancel?: () => void;
}

const MAX_INITIAL_STREAM_RETRIES = 1;
const INITIAL_STREAM_RETRY_DELAY_MS = 350;

export function compactQueuedEvents(events: DeepSpaceStreamEvent[]): DeepSpaceStreamEvent[] {
  return events;
}

export function useDeepSpaceStream({
  onEvent,
  onEvents,
  onTransportError,
  onFinally,
  onUserCancel,
}: UseDeepSpaceStreamOptions) {
  const abortRef = useRef<AbortController | null>(null);
  const cancelledByUserRef = useRef(false);
  const suppressFinallyRef = useRef(false);
  const onEventRef = useRef(onEvent);
  const onEventsRef = useRef(onEvents);
  const onTransportErrorRef = useRef(onTransportError);
  const onFinallyRef = useRef(onFinally);
  const onUserCancelRef = useRef(onUserCancel);

  onEventRef.current = onEvent;
  onEventsRef.current = onEvents;
  onTransportErrorRef.current = onTransportError;
  onFinallyRef.current = onFinally;
  onUserCancelRef.current = onUserCancel;

  const cancel = useCallback(() => {
    if (!abortRef.current) return;
    cancelledByUserRef.current = true;
    suppressFinallyRef.current = true;
    abortRef.current.abort();
    abortRef.current = null;
    onUserCancelRef.current?.();
  }, []);

  const start = useCallback(
    async ({ endpoint = "/deepspace/chats/stream", body }: StartStreamArgs) => {
      cancel();
      cancelledByUserRef.current = false;
      suppressFinallyRef.current = false;
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for (let attempt = 0; attempt <= MAX_INITIAL_STREAM_RETRIES; attempt += 1) {
          let receivedAnyEvent = false;
          try {
            const response = (await fetchWithAuth(endpoint, {
              method: "POST",
              body: JSON.stringify(body),
              signal: controller.signal,
              headers: { Accept: "text/event-stream", "Cache-Control": "no-cache" },
            })) as Response;

            if (!response.ok) {
              let message = `HTTP ${response.status}`;
              try {
                const payload = await response.clone().json();
                message = payload?.error?.message ?? payload?.detail ?? message;
              } catch {
                // Keep the HTTP fallback.
              }
              if (
                !receivedAnyEvent &&
                attempt < MAX_INITIAL_STREAM_RETRIES &&
                isRetryableStreamStatus(response.status)
              ) {
                await new Promise((resolve) =>
                  window.setTimeout(resolve, INITIAL_STREAM_RETRY_DELAY_MS),
                );
                continue;
              }
              onTransportErrorRef.current({ code: "STREAM_HTTP_ERROR", message });
              return;
            }

            const reader = response.body?.getReader();
            if (!reader) {
              onTransportErrorRef.current({
                code: "STREAM_BODY_MISSING",
                message: "Streaming response body is unavailable.",
              });
              return;
            }

            const decoder = new TextDecoder();
            let buffer = "";
            let terminalEventReceived = false;
            const dispatchEvents = (events: DeepSpaceStreamEvent[]) => {
              if (events.some((event) => event.event === "done" || event.event === "error")) {
                terminalEventReceived = true;
              }
              if (onEventsRef.current) onEventsRef.current(events);
              else events.forEach((event) => onEventRef.current(event));
            };
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              if (controller.signal.aborted) return;
              buffer += decoder.decode(value, { stream: true });
              const parsed = parseSseFrames(buffer);
              buffer = parsed.remainder;
              if (parsed.events.length > 0) {
                receivedAnyEvent = true;
                dispatchEvents(parsed.events);
              }
            }

            if (buffer.trim()) {
              const parsed = parseSseFrames(`${buffer}\n\n`);
              if (parsed.events.length > 0) {
                receivedAnyEvent = true;
                dispatchEvents(parsed.events);
              }
            }
            if (!terminalEventReceived && !controller.signal.aborted) {
              onTransportErrorRef.current({
                code: "STREAM_INCOMPLETE",
                message: receivedAnyEvent
                  ? "The chat provider closed the stream before completing the response."
                  : "The chat provider returned an empty stream.",
              });
            }
            return;
          } catch (error) {
            if (controller.signal.aborted) return;
            const retryable = isRetryableStreamTransportError(error);
            const message = normalizeStreamTransportMessage(
              error,
              "The chat stream could not be reached.",
              retryable,
            );
            if (attempt < MAX_INITIAL_STREAM_RETRIES && retryable) {
              await new Promise((resolve) =>
                window.setTimeout(resolve, INITIAL_STREAM_RETRY_DELAY_MS),
              );
              continue;
            }
            onTransportErrorRef.current({ code: "STREAM_TRANSPORT_ERROR", message });
            return;
          }
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        if (!suppressFinallyRef.current) onFinallyRef.current?.();
        suppressFinallyRef.current = false;
        cancelledByUserRef.current = false;
      }
    },
    [cancel],
  );

  return { start, cancel };
}
