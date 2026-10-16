/**
 * The provider's exact tokenizer is not available in the browser while a
 * response is streaming. Keep the live display honest by using the same
 * character-based estimate family as the server and labeling it as live
 * output until the provider reports its final usage.
 */
export interface LiveOutputSnapshot {
  rawContent?: string | null;
  content?: string | null;
  thinkingContent?: string | null;
  toolInputStreams?: Array<string | null | undefined>;
}

export function estimateLiveOutputTokens(snapshot: LiveOutputSnapshot | null | undefined): number {
  if (!snapshot) return 0;
  const answer = snapshot.rawContent || snapshot.content || "";
  const thinking = snapshot.thinkingContent ?? "";
  const toolArguments = (snapshot.toolInputStreams ?? []).reduce(
    (total, chunk) => total + (chunk?.length ?? 0),
    0,
  );
  const generatedCharacters = answer.length + thinking.length + toolArguments;
  return generatedCharacters > 0 ? Math.ceil(generatedCharacters / 4) : 0;
}

export function mergeOutputTokenEstimate(
  recordedTokens: number | null | undefined,
  liveEstimate: number,
): number {
  const recorded =
    typeof recordedTokens === "number" && Number.isFinite(recordedTokens)
      ? Math.max(0, recordedTokens)
      : 0;
  return Math.max(recorded, liveEstimate);
}

export function calculateLiveTokensPerSecond(
  outputTokens: number,
  startedAtMs: number | null,
  nowMs: number,
): number | null {
  if (
    outputTokens <= 0 ||
    startedAtMs === null ||
    !Number.isFinite(startedAtMs) ||
    !Number.isFinite(nowMs)
  ) {
    return outputTokens <= 0 && startedAtMs !== null ? 0 : null;
  }

  const elapsedMs = nowMs - startedAtMs;
  if (elapsedMs <= 0) return null;
  return outputTokens / (elapsedMs / 1000);
}
