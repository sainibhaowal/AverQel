import { describe, expect, it } from "vitest";

import {
  appendVoiceSpeechText,
  createVoiceSpeechAccumulator,
  voiceToolProgressText,
} from "../app/dashboard/deepspace/_lib/voice-speech";

describe("DeepSpace voice speech buffering", () => {
  it("waits for sentence boundaries across streamed text chunks", () => {
    const first = appendVoiceSpeechText(createVoiceSpeechAccumulator(), "I’ll check the ");
    expect(first.chunks).toEqual([]);

    const second = appendVoiceSpeechText(first.accumulator, "latest headlines. Found one.");
    expect(second.chunks).toEqual(["I’ll check the latest headlines."]);

    const final = appendVoiceSpeechText(second.accumulator, "", true);
    expect(final.chunks).toEqual(["Found one."]);
  });

  it("does not speak fenced code and turns markdown links into their visible label", () => {
    const result = appendVoiceSpeechText(
      createVoiceSpeechAccumulator(),
      "I found [a useful source](https://example.test). ```ts\nconst secret = true;\n``` The source is current.",
      true,
    );

    expect(result.chunks).toEqual(["I found a useful source.", "The source is current."]);
  });

  it("flushes a short progress update when the model starts a tool call", () => {
    const update = appendVoiceSpeechText(createVoiceSpeechAccumulator(), "I’m searching now");
    expect(update.chunks).toEqual([]);

    const flushed = appendVoiceSpeechText(update.accumulator, "", true);
    expect(flushed.chunks).toEqual(["I’m searching now"]);
  });

  it("uses brief user-facing progress text without exposing tool arguments", () => {
    expect(voiceToolProgressText("web_search")).toBe("I’m checking the latest sources now.");
    expect(voiceToolProgressText("url_read")).toBe("I’m opening a source to verify the details.");
    expect(voiceToolProgressText("write")).toBe("I’m working on the next step now.");
  });
});
