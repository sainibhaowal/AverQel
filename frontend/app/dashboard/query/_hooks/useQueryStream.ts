"use client";

import { useCallback, useEffect, useRef } from "react";

import { fetchWithAuth } from "@/lib/api";
import {
  isRetryableStreamStatus,
  isRetryableStreamTransportError,
  normalizeStreamTransportMessage,
} from "@/app/lib/streaming/sseTransport";

import { parseSseFrames, type QueryStreamEvent } from "../_lib/stream-protocol";

interface StartStreamArgs {
  endpoint?: string;
  method?: "POST";
  body: Record<string, unknown>;
}

interface UseQueryStreamOptions {
  onEvent: (event: QueryStreamEvent) => void;
  onTransportError: (error: { code: string; message: string }) => void;
  onFinally?: () => void;
  onUserCancel?: () => void;
}

const MAX_INITIAL_STREAM_RETRIES = 1;
const INITIAL_STREAM_RETRY_DELAY_MS = 350;

export function useQueryStream({
  onEvent,
  onTransportError,
  onFinally,
  onUserCancel,
}: UseQueryStreamOptions) {
  const abortRef = useRef<AbortController | null>(null);
  const cancelledByUserRef = useRef(false);
  const suppressFinallyRef = useRef(false);

  // Use refs for callbacks to stabilize the 'start' function.
  // This avoids re-creating the 'start' function if callbacks are not stable.
  const onEventRef = useRef(onEvent);
  const onTransportErrorRef = useRef(onTransportError);
  const onFinallyRef = useRef(onFinally);
  const onUserCancelRef = useRef(onUserCancel);

  useEffect(() => {
    onEventRef.current = onEvent;
    onTransportErrorRef.current = onTransportError;
    onFinallyRef.current = onFinally;
    onUserCancelRef.current = onUserCancel;
  }, [onEvent, onFinally, onTransportError, onUserCancel]);

  const cancel = useCallback(() => {
    if (!abortRef.current) {
      return;
    }
    cancelledByUserRef.current = true;
    suppressFinallyRef.current = true;
    abortRef.current?.abort();
    abortRef.current = null;
    onUserCancelRef.current?.();
  }, []);

  const start = useCallback(
    async ({ endpoint = "/queries/stream", method = "POST", body }: StartStreamArgs) => {
      cancel();
      cancelledByUserRef.current = false;
      suppressFinallyRef.current = false;
      const controller = new AbortController();
      abortRef.current = controller;
      const requestBody = JSON.stringify(body);

      try {
        for (let attempt = 0; attempt <= MAX_INITIAL_STREAM_RETRIES; attempt += 1) {
          let receivedAnyEvent = false;

          try {
            const response = (await fetchWithAuth(endpoint, {
              method,
              body: requestBody,
              signal: controller.signal,
              headers: {
                Accept: "text/event-stream",
                "Cache-Control": "no-cache",
              },
            })) as Response;

            if (!response.ok) {
              let message = `HTTP ${response.status}`;
              try {
                const payload = await response.clone().json();
                message = payload?.error?.message ?? payload?.detail ?? message;
              } catch {
                // Keep fallback message.
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

            while (true) {
              const { done, value } = await reader.read();
              if (done) {
                break;
              }

              buffer += decoder.decode(value, { stream: true });
              const parsed = parseSseFrames(buffer);
              buffer = parsed.remainder;
              for (const event of parsed.events) {
                if (controller.signal.aborted) {
                  return;
                }
                receivedAnyEvent = true;
                onEventRef.current(event);
              }
            }

            if (buffer.trim()) {
              const parsed = parseSseFrames(`${buffer}\n\n`);
              for (const event of parsed.events) {
                if (controller.signal.aborted) {
                  return;
                }
                receivedAnyEvent = true;
                onEventRef.current(event);
              }
            }

            return;
          } catch (error) {
            if (controller.signal.aborted) {
              if (cancelledByUserRef.current) {
                return;
              }
              return;
            }

            const retryable = !receivedAnyEvent && isRetryableStreamTransportError(error);
            if (retryable && attempt < MAX_INITIAL_STREAM_RETRIES) {
              await new Promise((resolve) =>
                window.setTimeout(resolve, INITIAL_STREAM_RETRY_DELAY_MS),
              );
              continue;
            }

            const message = normalizeStreamTransportMessage(
              error,
              "Network interruption during query streaming.",
              retryable,
            );
            onTransportErrorRef.current({ code: "STREAM_TRANSPORT_ERROR", message });
            return;
          }
        }
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
        cancelledByUserRef.current = false;
        if (!suppressFinallyRef.current) {
          onFinallyRef.current?.();
        }
        suppressFinallyRef.current = false;
      }
    },
    [cancel],
  );

  return { start, cancel };
}
