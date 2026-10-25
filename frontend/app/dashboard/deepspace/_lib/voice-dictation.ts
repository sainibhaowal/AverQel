export function appendDictationTranscript(baseText: string, transcript: string) {
  const cleanedTranscript = transcript.trim();
  if (!cleanedTranscript) return baseText;
  if (!baseText) return cleanedTranscript;
  return `${baseText}${baseText.endsWith(" ") ? "" : " "}${cleanedTranscript}`;
}

export function buildDictationPartialDraft(
  committedText: string,
  activeSegmentId: string | null,
  incomingSegmentId: string,
  transcript: string,
) {
  if (!activeSegmentId || incomingSegmentId !== activeSegmentId || !transcript.trim()) return null;
  return appendDictationTranscript(committedText, transcript);
}

export function commitDictationTranscript(
  committedText: string,
  activeSegmentId: string | null,
  incomingSegmentId: string,
  transcript: string,
) {
  if (!activeSegmentId || incomingSegmentId !== activeSegmentId || !transcript.trim()) return null;
  return appendDictationTranscript(committedText, transcript);
}
