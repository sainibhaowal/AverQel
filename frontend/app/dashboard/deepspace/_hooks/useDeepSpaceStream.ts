"use client";

import { useCallback, useRef } from "react";

import type { DeepSpaceStreamEvent } from "../_lib/deepspace-stream";
import {
  connectDeepSpaceWebSocketStream,
  type DeepSpaceWebSocketStreamHandle,
} from "../websocketIntegration";

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

export function compactQueuedEvents(events: DeepSpaceStreamEvent[]): DeepSpaceStreamEvent[] {
  if (events.length <= 1) {
    return events;
  }
  return events;
}

export function useDeepSpaceStream({
  onEvent,
  onEvents,
  onTransportError,
  onFinally,
  onUserCancel,
}: UseDeepSpaceStreamOptions) {
  const cancelledByUserRef = useRef(false);
  const suppressFinallyRef = useRef(false);
  const activeSocketRef = useRef<DeepSpaceWebSocketStreamHandle | null>(null);

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

  const resetStreamState = useCallback(() => {
    activeSocketRef.current?.close();
    activeSocketRef.current = null;
    suppressFinallyRef.current = true;
  }, []);

  const enqueueEvent = useCallback((event: DeepSpaceStreamEvent) => {
    if (cancelledByUserRef.current) return;
    if (onEventsRef.current) {
      onEventsRef.current([event]);
    } else {
      onEventRef.current(event);
    }
  }, []);

  const cancel = useCallback(() => {
    cancelledByUserRef.current = true;
    resetStreamState();
    onUserCancelRef.current?.();
  }, [resetStreamState]);

  const start = useCallback(
    async ({ endpoint = "/deepspace/chats/stream", body }: StartStreamArgs) => {
      resetStreamState();
      cancelledByUserRef.current = false;
      suppressFinallyRef.current = false;
      const socketHandle = connectDeepSpaceWebSocketStream({
        endpoint,
        body,
        onEvents: (events) => {
          if (cancelledByUserRef.current) return;
          for (const event of events) {
            enqueueEvent(event);
          }
        },
        onTransportError: (error) => {
          if (!cancelledByUserRef.current) {
            onTransportErrorRef.current(error);
          }
        },
      });

      if (!socketHandle) {
        return;
      }

      activeSocketRef.current = socketHandle;
      try {
        await socketHandle.closed;
      } finally {
        if (activeSocketRef.current === socketHandle) {
          activeSocketRef.current = null;
        }
        cancelledByUserRef.current = false;
        if (!suppressFinallyRef.current) {
          onFinallyRef.current?.();
        }
        suppressFinallyRef.current = false;
      }
    },
    [enqueueEvent, resetStreamState],
  );

  const resume = useCallback(
    async (args: { conversationId: string; stepId: string; toolId: string; approved: boolean; durableRunId?: string; approvalId?: string }) => {
      return start({
        endpoint: "/deepspace/chats/resume",
        body: {
          conversation_id: args.conversationId,
          step_id: args.stepId,
          tool_id: args.toolId,
          approved: args.approved,
          durable_run_id: args.durableRunId,
          approval_id: args.approvalId,
        },
      });
    },
    [start],
  );

  return { start, cancel, resume };
}
