"use client";

import { useEffect, useState } from "react";
import { calculateLiveTokensPerSecond } from "../_lib/live-token-metrics";

interface DeepSpaceLiveOutputRateProps {
  outputTokens: number;
  startedAtMs: number | null;
}

/** Keep the periodic speed display local so its clock does not rerender the chat page. */
export default function DeepSpaceLiveOutputRate({
  outputTokens,
  startedAtMs,
}: DeepSpaceLiveOutputRateProps) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  const tokensPerSecond = calculateLiveTokensPerSecond(outputTokens, startedAtMs, nowMs);

  return (
    <>
      {" · "}~{typeof tokensPerSecond === "number" ? tokensPerSecond.toFixed(1) : "0.0"} tok/s
    </>
  );
}
