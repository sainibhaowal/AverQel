import { describe, expect, it } from "vitest";

import {
  calculateLiveTokensPerSecond,
  estimateLiveOutputTokens,
  mergeOutputTokenEstimate,
} from "../app/dashboard/deepspace/_lib/live-token-metrics";

describe("live DeepSpace token metrics", () => {
  it("counts answer and reasoning chunks while a response is streaming", () => {
    expect(
      estimateLiveOutputTokens({
        rawContent: "abcdefgh",
        thinkingContent: "ijkl",
      }),
    ).toBe(3);
  });

  it("includes streamed function arguments while the model is calling a tool", () => {
    expect(
      estimateLiveOutputTokens({
        toolInputStreams: ["abcdefgh", "ij"],
      }),
    ).toBe(3);
  });

  it("does not regress when a server round metric is already cumulative", () => {
    expect(mergeOutputTokenEstimate(8, 5)).toBe(8);
    expect(mergeOutputTokenEstimate(8, 11)).toBe(11);
    expect(mergeOutputTokenEstimate(null, 4)).toBe(4);
  });

  it("calculates a live average rate from the stream start", () => {
    expect(calculateLiveTokensPerSecond(20, 1_000, 3_000)).toBe(10);
    expect(calculateLiveTokensPerSecond(0, 1_000, 3_000)).toBe(0);
    expect(calculateLiveTokensPerSecond(20, null, 3_000)).toBeNull();
  });
});
