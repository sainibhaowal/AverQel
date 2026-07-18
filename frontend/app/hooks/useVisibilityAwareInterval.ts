"use client";

import { useEffect, useRef } from "react";

type IntervalOptions = {
  immediate?: boolean;
};

export function useVisibilityAwareInterval(
  callback: () => void,
  delayMs: number | null,
  options: IntervalOptions = {},
) {
  const callbackRef = useRef(callback);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (delayMs === null) {
      return;
    }

    const stop = () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };

    const start = () => {
      if (intervalRef.current !== null || document.hidden) {
        return;
      }

      if (options.immediate) {
        callbackRef.current();
      }

      intervalRef.current = window.setInterval(() => {
        if (!document.hidden) {
          callbackRef.current();
        }
      }, delayMs);
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stop();
        return;
      }

      start();
    };

    start();
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      stop();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [delayMs, options.immediate]);
}
