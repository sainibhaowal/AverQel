export type VoiceSpeechAccumulator = {
  sourceRemainder: string;
  speechRemainder: string;
  inCodeBlock: boolean;
};

export function createVoiceSpeechAccumulator(): VoiceSpeechAccumulator {
  return { sourceRemainder: "", speechRemainder: "", inCodeBlock: false };
}

export function voiceToolProgressText(toolName: unknown): string {
  switch (String(toolName ?? "").toLowerCase()) {
    case "web_search":
      return "I’m checking the latest sources now.";
    case "url_read":
      return "I’m opening a source to verify the details.";
    case "image_read":
      return "I’m reviewing the image now.";
    default:
      return "I’m working on the next step now.";
  }
}

function plainSpeechText(text: string): string {
  return text
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, " $1 ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/`/g, "")
    .replace(/[*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function splitSpeakableSentences(text: string, flush: boolean): { chunks: string[]; rest: string } {
  const chunks: string[] = [];
  let rest = text;

  while (rest) {
    const match = /[.!?](?:["')\]]*)\s+/.exec(rest);
    let end = match ? match.index + match[0].length : -1;
    if (end < 0 && rest.length > 240) {
      const splitAt = rest.lastIndexOf(" ", 240);
      if (splitAt > 80) end = splitAt;
    }
    if (end < 0) break;

    const sentence = plainSpeechText(rest.slice(0, end));
    if (sentence) chunks.push(sentence);
    rest = rest.slice(end).trimStart();
  }

  if (flush && rest) {
    const finalChunk = plainSpeechText(rest);
    if (finalChunk) chunks.push(finalChunk);
    rest = "";
  }

  return { chunks, rest };
}

export function appendVoiceSpeechText(
  accumulator: VoiceSpeechAccumulator,
  delta: string,
  flush = false,
): { chunks: string[]; accumulator: VoiceSpeechAccumulator } {
  const source = accumulator.sourceRemainder + delta;
  let cursor = 0;
  let inCodeBlock = accumulator.inCodeBlock;
  let visibleText = "";

  while (true) {
    const markerIndex = source.indexOf("```", cursor);
    if (markerIndex < 0) break;
    if (!inCodeBlock) visibleText += source.slice(cursor, markerIndex);
    inCodeBlock = !inCodeBlock;
    cursor = markerIndex + 3;
  }

  let sourceRemainder = "";
  const tail = source.slice(cursor);
  if (!flush) {
    const trailingBackticks = tail.match(/`{1,2}$/)?.[0] ?? "";
    if (!inCodeBlock) {
      visibleText += trailingBackticks ? tail.slice(0, -trailingBackticks.length) : tail;
    }
    sourceRemainder = trailingBackticks;
  } else if (!inCodeBlock) {
    visibleText += tail;
  }

  const split = splitSpeakableSentences(
    `${accumulator.speechRemainder}${visibleText}`,
    flush && !inCodeBlock,
  );
  return {
    chunks: split.chunks,
    accumulator: {
      sourceRemainder,
      speechRemainder: split.rest,
      inCodeBlock,
    },
  };
}
