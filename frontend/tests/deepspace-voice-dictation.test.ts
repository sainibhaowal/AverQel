import { describe, expect, it } from "vitest";

import {
  buildDictationPartialDraft,
  commitDictationTranscript,
} from "../app/dashboard/deepspace/_lib/voice-dictation";

describe("DeepSpace dictation transcript updates", () => {
  it("replaces interim snapshots instead of appending every partial version", () => {
    const firstPartial = buildDictationPartialDraft("Existing draft", "4", "4", "check the");
    const revisedPartial = buildDictationPartialDraft("Existing draft", "4", "4", "check the news");

    expect(firstPartial).toBe("Existing draft check the");
    expect(revisedPartial).toBe("Existing draft check the news");
  });

  it("ignores a partial or final result that belongs to an older speech segment", () => {
    expect(buildDictationPartialDraft("Saved text", "8", "7", "stale words")).toBeNull();
    expect(commitDictationTranscript("Saved text", "8", "7", "stale words")).toBeNull();
  });

  it("commits the final phrase once and keeps existing composer text", () => {
    const committed = commitDictationTranscript("Saved text", "9", "9", "you can hear me");
    expect(committed).toBe("Saved text you can hear me");
    expect(commitDictationTranscript(committed ?? "", null, "9", "you can hear me")).toBeNull();
    expect(commitDictationTranscript("Saved text", "9", "9", "   ")).toBeNull();
  });
});
