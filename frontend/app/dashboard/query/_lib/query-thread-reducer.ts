import type { ReasoningTraceData } from "@/app/components/query/ReasoningTrace";

import {
  createClientMessageId,
  extractArtifactsFromContent,
  parseStructuredAnswer,
  structuredAnswerToMarkdown,
  type CitationItem,
  type QueryHistoryMessage,
  type QueryStatusEntry,
  type QueryHistoryVersion,
  type QueryStreamEvent,
  type QueryThreadMessage,
  type QueryThreadMessageVersion,
  type StructuredAnswerShape,
  type StructuredBlock,
  estimateTokens,
} from "./stream-protocol";
import { normalizeMarkdown } from "./markdown";

export interface QueryThreadState {
  messages: QueryThreadMessage[];
  messageIndex: Map<string, number>;
  currentConversationId: string | null;
  activeAssistantId: string | null;
  isStreaming: boolean;
  streamError: { code: string; message: string } | null;
  lastModelName: string | null;
}

export type QueryThreadAction =
  | { type: "load_history"; conversationId: string; messages: QueryHistoryMessage[] }
  | { type: "reset_thread" }
  | { type: "submit_query"; query: string }
  | { type: "start_regenerate"; assistantMessageId: string }
  | { type: "start_edit"; messageId: string }
  | { type: "cancel_edit"; messageId: string }
  | { type: "update_edit_draft"; messageId: string; value: string }
  | { type: "commit_user_edit"; messageId: string; content: string }
  | { type: "activate_version"; messageId: string; versionId: string }
  | { type: "delete_message_local"; messageId: string }
  | { type: "stream_interrupted" }
  | { type: "stream_event"; event: QueryStreamEvent }
  | { type: "stream_finished" }
  | { type: "stream_failed"; error: { code: string; message: string } };

export const initialQueryThreadState: QueryThreadState = {
  messages: [],
  messageIndex: new Map(),
  currentConversationId: null,
  activeAssistantId: null,
  isStreaming: false,
  streamError: null,
  lastModelName: null,
};

function mergeUniqueCitations(existing: CitationItem[], incoming: CitationItem): CitationItem[] {
  if (existing.some((item) => item.chunk_id === incoming.chunk_id)) {
    return existing;
  }
  return [...existing, incoming];
}

function mergeUniqueBlocks(
  existing: StructuredBlock[],
  incoming: StructuredBlock,
): StructuredBlock[] {
  const index = existing.findIndex(
    (block) => block.id === incoming.id && block.type === incoming.type,
  );
  if (index === -1) {
    return [...existing, incoming];
  }
  const current = existing[index];
  if (JSON.stringify(current) === JSON.stringify(incoming)) {
    return existing;
  }
  const next = [...existing];
  next[index] = incoming;
  return next;
}

function normalizeIncomingBlock(incoming: StructuredBlock): StructuredBlock {
  if (incoming.type !== "diagram") {
    return incoming;
  }

  return {
    ...incoming,
    diagram_type: incoming.diagram_type ?? "mermaid_flowchart",
    source: incoming.source ?? "mermaid",
    syntax: incoming.syntax ?? "",
    description: incoming.description ?? "",
  };
}

function normalizeDetail(v?: string): string {
  return v ?? "";
}

function appendStatusEntry(
  history: QueryThreadMessageVersion["statusHistory"],
  entry: QueryStatusEntry,
): QueryThreadMessageVersion["statusHistory"] {
  const last = history[history.length - 1];
  if (
    last &&
    (last.code ?? "") === (entry.code ?? "") &&
    last.label === entry.label &&
    last.state === entry.state &&
    normalizeDetail(last.detail) === normalizeDetail(entry.detail)
  ) {
    return history;
  }
  return [...history, entry];
}

function createInitialStatusEntry(timestamp: string): QueryStatusEntry {
  return {
    code: "retrieval",
    label: "Retrieving Evidence",
    state: "running",
    detail: "Starting query pipeline",
    timestamp,
  };
}

function buildMessageIndex(messages: QueryThreadMessage[]): Map<string, number> {
  const map = new Map<string, number>();
  messages.forEach((msg, index) => map.set(msg.id, index));
  return map;
}

function parseAssistantContent(raw: string): {
  content: string;
  structured: StructuredAnswerShape | null;
} {
  const structured = parseStructuredAnswer(raw);
  if (!structured) {
    return { content: normalizeMarkdown(raw), structured: null };
  }
  return { content: structuredAnswerToMarkdown(structured), structured };
}

function coerceTrace(metadata: Record<string, unknown> | undefined): ReasoningTraceData | null {
  const candidate = metadata?.reasoning_trace;
  if (!candidate || typeof candidate !== "object") {
    return null;
  }
  return candidate as ReasoningTraceData;
}

function versionFromHistory(
  role: "user" | "assistant",
  version: QueryHistoryVersion,
): QueryThreadMessageVersion {
  const metadata = (version.metadata_json ?? {}) as Record<string, unknown>;
  const structuredFromMetadata =
    role === "assistant" &&
    metadata.structured_answer &&
    typeof metadata.structured_answer === "object"
      ? (metadata.structured_answer as StructuredAnswerShape)
      : null;
  const assistantPayload =
    role === "assistant"
      ? structuredFromMetadata
        ? {
            content: structuredAnswerToMarkdown(structuredFromMetadata),
            structured: structuredFromMetadata,
          }
        : parseAssistantContent(version.content)
      : { content: version.content, structured: null };

  return {
    id: version.id,
    versionIndex: version.version_index,
    sourceType: version.source_type,
    createdAt: version.created_at,
    content: assistantPayload.content,
    rawContent: version.content,
    citations: Array.isArray(metadata.citations) ? (metadata.citations as CitationItem[]) : [],
    blocks: Array.isArray(metadata.blocks) ? (metadata.blocks as StructuredBlock[]) : [],
    artifacts: extractArtifactsFromContent(assistantPayload.content),
    trace: coerceTrace(metadata),
    followups: Array.isArray(metadata.follow_up_suggestions)
      ? (metadata.follow_up_suggestions as string[])
      : [],
    statusHistory: Array.isArray(metadata.status_history)
      ? (metadata.status_history as QueryThreadMessageVersion["statusHistory"])
      : [],
    output: Array.isArray(metadata.output)
      ? (metadata.output as QueryThreadMessageVersion["output"])
      : [],
    files: Array.isArray(metadata.files)
      ? (metadata.files as QueryThreadMessageVersion["files"])
      : [],
    thinkingContent:
      metadata.thinking && typeof metadata.thinking === "object"
        ? String((metadata.thinking as Record<string, unknown>).content ?? "")
        : undefined,
    confidence: typeof metadata.confidence === "number" ? metadata.confidence : undefined,
    traceId: typeof metadata.trace_id === "string" ? metadata.trace_id : undefined,
    cached: typeof metadata.cached === "boolean" ? metadata.cached : undefined,
    structured: assistantPayload.structured,
    error: null,
    status: "ready",
  };
}

function applyVersionToMessage(
  message: QueryThreadMessage,
  version: QueryThreadMessageVersion,
): QueryThreadMessage {
  return {
    ...message,
    content: version.content,
    rawContent: version.rawContent,
    status: version.status,
    streamPhase: version.streamPhase,
    citations: version.citations,
    blocks: version.blocks,
    artifacts: version.artifacts,
    trace: version.trace,
    followups: version.followups,
    statusHistory: version.statusHistory,
    output: version.output,
    files: version.files,
    thinkingContent: version.thinkingContent,
    confidence: version.confidence,
    traceId: version.traceId,
    cached: version.cached,
    structured: version.structured,
    error: version.error,
    activeVersionId: version.id,
    activeVersionIndex: version.versionIndex,
    versionCount: message.versions.length,
  };
}

function fromHistoryMessage(message: QueryHistoryMessage): QueryThreadMessage {
  const versions =
    message.versions && message.versions.length > 0
      ? [...message.versions]
          .sort((a, b) => a.version_index - b.version_index)
          .map((version) => versionFromHistory(message.role, version))
      : [
          versionFromHistory(message.role, {
            id: message.active_version_id ?? `${message.id}-v1`,
            version_index: message.active_version_index ?? 1,
            content: message.content,
            metadata_json: message.metadata_json,
            source_type: "initial",
            created_at: message.created_at,
          }),
        ];

  const activeVersion =
    versions.find((version) => version.id === message.active_version_id) ??
    versions.find((version) => version.versionIndex === (message.active_version_index ?? 1)) ??
    versions[versions.length - 1];

  return applyVersionToMessage(
    {
      id: message.id,
      role: message.role,
      content: "",
      rawContent: "",
      createdAt: message.created_at,
      status: "ready",
      citations: [],
      blocks: [],
      artifacts: [],
      trace: null,
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      thinkingContent: undefined,
      structured: null,
      error: null,
      activeVersionId: activeVersion?.id ?? null,
      activeVersionIndex: activeVersion?.versionIndex ?? 1,
      versionCount: versions.length,
      versions,
      isEditing: false,
      draftContent: message.role === "user" ? message.content : undefined,
    },
    activeVersion ?? versions[0],
  );
}

function captureActiveVersion(message: QueryThreadMessage): QueryThreadMessageVersion {
  return {
    id: message.activeVersionId ?? `${message.id}-active`,
    versionIndex: message.activeVersionIndex,
    sourceType:
      message.versions.find((version) => version.id === message.activeVersionId)?.sourceType ??
      "initial",
    createdAt: message.createdAt,
    content: message.content,
    rawContent: message.rawContent ?? message.content,
    citations: message.citations,
    blocks: message.blocks,
    artifacts: message.artifacts,
    trace: message.trace,
    followups: message.followups,
    statusHistory: message.statusHistory,
    output: message.output,
    files: message.files,
    thinkingContent: message.thinkingContent,
    confidence: message.confidence,
    traceId: message.traceId,
    cached: message.cached,
    structured: message.structured,
    error: message.error,
    status: message.status,
    streamPhase: message.streamPhase,
  };
}

function createUserMessage(query: string): QueryThreadMessage {
  const versionId = createClientMessageId("user");
  const version: QueryThreadMessageVersion = {
    id: versionId,
    versionIndex: 1,
    sourceType: "initial",
    createdAt: new Date().toISOString(),
    content: query,
    rawContent: query,
    citations: [],
    blocks: [],
    artifacts: [],
    trace: null,
    followups: [],
    statusHistory: [],
    output: [],
    files: [],
    thinkingContent: undefined,
    structured: null,
    error: null,
    status: "ready",
  };

  return {
    id: createClientMessageId("user"),
    role: "user",
    content: query,
    rawContent: query,
    createdAt: version.createdAt,
    status: "ready",
    citations: [],
    blocks: [],
    artifacts: [],
    trace: null,
    followups: [],
    statusHistory: [],
    output: [],
    files: [],
    thinkingContent: undefined,
    structured: null,
    error: null,
    activeVersionId: version.id,
    activeVersionIndex: 1,
    versionCount: 1,
    versions: [version],
    isEditing: false,
    draftContent: query,
  };
}

function createAssistantPlaceholder(messageId?: string): QueryThreadMessage {
  const createdAt = new Date().toISOString();
  const versionId = createClientMessageId("assistant");
  const initialStatus = createInitialStatusEntry(createdAt);
  const version: QueryThreadMessageVersion = {
    id: versionId,
    versionIndex: 1,
    sourceType: "initial",
    createdAt,
    content: "",
    rawContent: "",
    citations: [],
    blocks: [],
    artifacts: [],
    trace: null,
    followups: [],
    statusHistory: [initialStatus],
    output: [],
    files: [],
    thinkingContent: undefined,
    structured: null,
    error: null,
    status: "streaming",
    streamPhase: "searching",
  };

  return {
    id: messageId ?? createClientMessageId("assistant"),
    role: "assistant",
    content: "",
    rawContent: "",
    createdAt,
    status: "streaming",
    streamPhase: "searching",
    citations: [],
    blocks: [],
    artifacts: [],
    trace: null,
    followups: [],
    statusHistory: version.statusHistory,
    output: [],
    files: [],
    structured: null,
    error: null,
    activeVersionId: versionId,
    activeVersionIndex: 1,
    versionCount: 1,
    versions: [version],
  };
}

function updateMessage(
  state: QueryThreadState,
  messageId: string,
  updater: (message: QueryThreadMessage) => QueryThreadMessage,
): QueryThreadState {
  const idx = state.messageIndex.get(messageId);
  if (idx === undefined) {
    return state;
  }
  const current = state.messages[idx];
  if (!current) {
    return state;
  }
  const updated = updater(current);
  if (updated === current) {
    return state;
  }
  const messages = [...state.messages];
  messages[idx] = updated;
  return { ...state, messages };
}

function updateActiveVersion(
  message: QueryThreadMessage,
  updater: (version: QueryThreadMessageVersion) => QueryThreadMessageVersion,
): QueryThreadMessage {
  const activeId = message.activeVersionId ?? message.versions[message.versions.length - 1]?.id;
  if (!activeId) {
    return message;
  }
  const index = message.versions.findIndex((version) => version.id === activeId);
  if (index === -1) {
    return message;
  }
  const currentVersion = message.versions[index];
  const nextVersion = updater(currentVersion);
  if (nextVersion === currentVersion) {
    return message;
  }
  const versions = [...message.versions];
  versions[index] = nextVersion;
  return applyVersionToMessage(
    { ...message, versions, versionCount: versions.length },
    nextVersion,
  );
}

function appendAssistantVersion(
  message: QueryThreadMessage,
  sourceType: string,
): QueryThreadMessage {
  const nextVersionIndex =
    Math.max(0, ...message.versions.map((version) => version.versionIndex)) + 1;
  const createdAt = new Date().toISOString();
  const version: QueryThreadMessageVersion = {
    id: createClientMessageId("assistant"),
    versionIndex: nextVersionIndex,
    sourceType,
    createdAt,
    content: "",
    rawContent: "",
    citations: [],
    blocks: [],
    artifacts: [],
    trace: null,
    followups: [],
    statusHistory: [createInitialStatusEntry(createdAt)],
    output: [],
    files: [],
    structured: null,
    error: null,
    status: "streaming",
    streamPhase: "searching",
  };
  const versions = [...message.versions, version];
  return applyVersionToMessage({ ...message, versions, versionCount: versions.length }, version);
}

function appendUserVersion(message: QueryThreadMessage, content: string): QueryThreadMessage {
  const version: QueryThreadMessageVersion = {
    ...captureActiveVersion(message),
    id: createClientMessageId("user"),
    versionIndex: Math.max(0, ...message.versions.map((item) => item.versionIndex)) + 1,
    sourceType: "user_edit",
    createdAt: new Date().toISOString(),
    content,
    rawContent: content,
    status: "ready",
    streamPhase: undefined,
    error: null,
  };
  const versions = [...message.versions, version];
  return applyVersionToMessage(
    {
      ...message,
      versions,
      versionCount: versions.length,
      isEditing: false,
      draftContent: content,
    },
    version,
  );
}

function activateVersionById(message: QueryThreadMessage, versionId: string): QueryThreadMessage {
  const version = message.versions.find((item) => item.id === versionId);
  if (!version) {
    return message;
  }
  return applyVersionToMessage({ ...message }, version);
}

function resolveTargetAssistantId(state: QueryThreadState, event: QueryStreamEvent): string | null {
  if (event.event === "start" && event.data.operation && event.data.operation !== "new_turn") {
    return event.data.message_id;
  }
  if (event.event === "meta" && event.data.message_id) {
    return event.data.message_id;
  }
  return state.activeAssistantId ?? findLastAssistantId(state.messages);
}

function findLastAssistantId(messages: QueryThreadMessage[]): string | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i]?.role === "assistant") {
      return messages[i]!.id;
    }
  }
  return null;
}

export function queryThreadReducer(
  state: QueryThreadState,
  action: QueryThreadAction,
): QueryThreadState {
  switch (action.type) {
    case "reset_thread":
      return initialQueryThreadState;

    case "load_history": {
      const messages = action.messages.map(fromHistoryMessage);
      return {
        ...state,
        messages,
        messageIndex: buildMessageIndex(messages),
        currentConversationId: action.conversationId,
        activeAssistantId: null,
        isStreaming: false,
        streamError: null,
        lastModelName:
          (action.messages.findLast((m) => m.role === "assistant")?.metadata_json
            ?.model_name as string) || null,
      };
    }

    case "submit_query": {
      const user = createUserMessage(action.query);
      const assistant = createAssistantPlaceholder();
      const messages = [...state.messages, user, assistant];
      return {
        ...state,
        messages,
        messageIndex: buildMessageIndex(messages),
        activeAssistantId: assistant.id,
        isStreaming: true,
        streamError: null,
      };
    }

    case "start_regenerate":
      return updateMessage(
        {
          ...state,
          activeAssistantId: action.assistantMessageId,
          isStreaming: true,
          streamError: null,
        },
        action.assistantMessageId,
        (message) => appendAssistantVersion(message, "regenerate"),
      );

    case "start_edit":
      return updateMessage(state, action.messageId, (message) => ({
        ...message,
        isEditing: true,
        draftContent: message.content,
      }));

    case "cancel_edit":
      return updateMessage(state, action.messageId, (message) => ({
        ...message,
        isEditing: false,
        draftContent: message.content,
      }));

    case "update_edit_draft":
      return updateMessage(state, action.messageId, (message) => ({
        ...message,
        draftContent: action.value,
      }));

    case "commit_user_edit":
      return updateMessage(state, action.messageId, (message) =>
        appendUserVersion(message, action.content),
      );

    case "activate_version":
      return updateMessage(state, action.messageId, (message) =>
        activateVersionById(message, action.versionId),
      );

    case "delete_message_local": {
      const messages = state.messages.filter((message) => message.id !== action.messageId);
      return {
        ...state,
        messages,
        messageIndex: buildMessageIndex(messages),
        activeAssistantId:
          state.activeAssistantId === action.messageId ? null : state.activeAssistantId,
        isStreaming: state.activeAssistantId === action.messageId ? false : state.isStreaming,
      };
    }

    case "stream_interrupted": {
      const interruptedId = state.activeAssistantId;
      if (!interruptedId) {
        return { ...state, isStreaming: false, activeAssistantId: null, streamError: null };
      }
      return updateMessage(
        { ...state, isStreaming: false, activeAssistantId: null, streamError: null },
        interruptedId,
        (message) => {
          const activeVersion = message.versions.find(
            (item) => item.id === message.activeVersionId,
          );
          const hasContent = Boolean((activeVersion?.content ?? message.content).trim());

          if (!hasContent) {
            if (message.versions.length > 1) {
              const versions = message.versions.slice(0, -1);
              const fallback = versions[versions.length - 1];
              return fallback
                ? applyVersionToMessage(
                    {
                      ...message,
                      versions,
                      versionCount: versions.length,
                    },
                    fallback,
                  )
                : message;
            }
            return message;
          }

          return updateActiveVersion(message, (version) => ({
            ...version,
            status: "ready",
            streamPhase: undefined,
            artifacts: extractArtifactsFromContent(version.content),
            statusHistory: appendStatusEntry(version.statusHistory, {
              label: "Stopped",
              state: "completed",
            }),
          }));
        },
      );
    }

    case "stream_event": {
      const targetAssistantId = resolveTargetAssistantId(state, action.event);
      switch (action.event.event) {
        case "start": {
          const {
            message_id,
            conversation_id,
            started_at,
            operation: op = "new_turn",
          } = action.event.data;

          if (op === "new_turn") {
            return {
              ...state,
              currentConversationId: conversation_id,
              isStreaming: true,
              streamError: null,
            };
          }
          const stateWithTarget = {
            ...state,
            currentConversationId: conversation_id,
            activeAssistantId: message_id,
            isStreaming: true,
            streamError: null,
          };
          return updateMessage(stateWithTarget, message_id, (message) => {
            if (message.status === "streaming") {
              return message;
            }
            const startedAt = started_at;
            const updated = appendAssistantVersion(
              message,
              op === "edit_regenerate" ? "regenerate" : "regenerate",
            );
            return updateActiveVersion(updated, (version) => ({
              ...version,
              metrics: { ...version.metrics, startedAt },
            }));
          });
        }

        case "meta": {
          const { conversation_id, confidence, trace_id, cached, model_name, provider_type } =
            action.event.data;
          if (!targetAssistantId) return state;
          const nextState = {
            ...state,
            currentConversationId: conversation_id,
            activeAssistantId: targetAssistantId,
            lastModelName: (model_name as string) || state.lastModelName,
          };
          return updateMessage(nextState, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              confidence: confidence,
              traceId: trace_id,
              cached: cached,
              streamPhase: "grounding",
              metrics: {
                ...version.metrics,
                modelName: model_name,
                providerType: provider_type,
              },
              statusHistory: appendStatusEntry(version.statusHistory, {
                label: "Grounding",
                state: "running",
              }),
            })),
          );
        }

        case "metrics": {
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              metrics: { ...version.metrics, ...action.event.data },
            })),
          );
        }

        case "thinking": {
          const thinking = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              thinkingContent: `${version.thinkingContent ?? ""}${thinking.text}`,
              status: "streaming",
              streamPhase: "grounding",
              statusHistory: appendStatusEntry(version.statusHistory, {
                label: "Thinking",
                state: "running",
              }),
            })),
          );
        }

        case "delta": {
          const delta = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => {
              const raw = (version.rawContent ?? "") + delta.text;
              // Progressive structured answer extraction:
              // During streaming the backend emits raw JSON tokens.  Passing
              // that JSON verbatim to the markdown renderer causes text to be
              // trapped inside CODE blocks (the parser sees backticks/braces
              // in the JSON and misidentifies them).  We try to parse or
              // extract the detailed_analysis field so the user sees clean
              // markdown even while the stream is still in flight.
              let displayContent: string;
              const trimmed = raw.trimStart();
              if (trimmed.startsWith("{")) {
                // Try full JSON parse first (works once the JSON is complete)
                const structured = parseStructuredAnswer(raw);
                if (structured) {
                  displayContent = structuredAnswerToMarkdown(structured);
                } else {
                  // Fallback: regex-extract "detailed_analysis" and "diagram" so far.
                  // Prepending the diagram ensures it stays at the top throughout streaming.
                  const detailMatch = raw.match(
                    /"detailed_analysis"\s*:\s*"([\s\S]*?)(?:"\s*[,}]|$)/,
                  );
                  const diagramMatch = raw.match(
                    /"diagram"\s*:\s*\{"syntax"\s*:\s*"([\s\S]*?)(?:"\s*[,}]|$)/,
                  );

                  let analysisText = "";
                  if (detailMatch) {
                    analysisText = detailMatch[1]
                      .replace(/\\n/g, "\n")
                      .replace(/\\t/g, "\t")
                      .replace(/\\"/g, '"')
                      .replace(/\\\\/g, "\\");
                  }

                  if (diagramMatch) {
                    let diagramSyntax = diagramMatch[1]
                      .replace(/\\n/g, "\n")
                      .replace(/\\t/g, "\t")
                      .replace(/\\"/g, '"')
                      .replace(/\\\\/g, "\\");
                    diagramSyntax = diagramSyntax.trim();

                    if (diagramSyntax) {
                      // STRIP the inline mermaid block from analysisText if it matches diagramSyntax
                      // We use a signature approach to be robust against partial streams
                      const getSignature = (t: string) =>
                        t.replace(/\s+/g, "").replace(/['"]/g, "");
                      const syntaxSig = getSignature(diagramSyntax);

                      const strippedAnalysis = analysisText.replace(
                        /```mermaid\s*([\s\S]*?)(?:```|$)/g,
                        (match, blockContent) => {
                          if (
                            getSignature(blockContent.trim()).startsWith(syntaxSig) ||
                            syntaxSig.startsWith(getSignature(blockContent.trim()))
                          ) {
                            return ""; // Strip the matching or partial matching inline block
                          }
                          return match;
                        },
                      );

                      displayContent = `### Generated Diagram\n\n\`\`\`mermaid\n${diagramSyntax}\n\`\`\`\n\n${strippedAnalysis}`;
                    } else {
                      displayContent = analysisText;
                    }
                  } else {
                    displayContent = analysisText || version.content;
                  }
                }
              } else {
                displayContent = normalizeMarkdown(raw);
              }
              // Metrics calculation
              const now = Date.now();
              const metrics = { ...(version.metrics || {}) };

              if (!metrics.firstTokenAt && delta.text.trim()) {
                metrics.firstTokenAt = new Date(now).toISOString();
                if (metrics.startedAt) {
                  metrics.ttftMs = now - new Date(metrics.startedAt).getTime();
                }
              }

              const totalTokens = estimateTokens(raw);
              metrics.totalTokens = totalTokens;

              if (metrics.firstTokenAt) {
                const durationSec = (now - new Date(metrics.firstTokenAt).getTime()) / 1000;
                if (durationSec > 0.1) {
                  metrics.tokensPerSec = Math.round((totalTokens / durationSec) * 10) / 10;
                }
              }

              return {
                ...version,
                rawContent: raw,
                content: displayContent,
                status: "streaming",
                streamPhase: "answering",
                metrics,
                statusHistory: appendStatusEntry(version.statusHistory, {
                  label: "Answering",
                  state: "running",
                }),
                error: null,
              };
            }),
          );
        }

        case "replace": {
          const replace = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => {
              const normalized = normalizeMarkdown(replace.content);
              return {
                ...version,
                rawContent: replace.content,
                content: normalized,
                structured: replace.structured ?? null,
                streamPhase: "answering",
              };
            }),
          );
        }

        case "citation": {
          const citation = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              citations: mergeUniqueCitations(version.citations, citation.item),
            })),
          );
        }

        case "table":
        case "chart":
        case "card":
        case "diagram":
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              blocks: mergeUniqueBlocks(
                version.blocks,
                normalizeIncomingBlock({
                  ...action.event.data,
                  type: action.event.event,
                } as StructuredBlock),
              ),
            })),
          );

        case "status": {
          const status = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => {
              const labelLower = status.label.toLowerCase();
              let nextPhase: QueryThreadMessage["streamPhase"] = version.streamPhase;
              if (labelLower.includes("search")) nextPhase = "searching";
              else if (labelLower.includes("ground") || labelLower.includes("cit"))
                nextPhase = "grounding";
              else if (labelLower.includes("answer") || labelLower.includes("respond"))
                nextPhase = "answering";
              return {
                ...version,
                streamPhase: nextPhase,
                statusHistory: appendStatusEntry(version.statusHistory, {
                  code: status.code,
                  label: status.label,
                  state: status.state ?? "running",
                  detail: status.detail,
                  timestamp: status.timestamp,
                  durationMs: status.duration_ms,
                }),
              };
            }),
          );
        }

        case "files": {
          const files = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              files: files.items,
            })),
          );
        }

        case "output": {
          const output = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              output: output.items,
            })),
          );
        }

        case "trace": {
          const trace = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              trace: trace.trace,
            })),
          );
        }

        case "followups": {
          const followups = action.event.data;
          if (!targetAssistantId) return state;
          return updateMessage(state, targetAssistantId, (message) =>
            updateActiveVersion(message, (version) => ({
              ...version,
              followups: followups.items,
            })),
          );
        }

        case "error": {
          const error = action.event.data;
          if (!targetAssistantId) {
            return {
              ...state,
              isStreaming: false,
              activeAssistantId: null,
              streamError: { code: error.code, message: error.message },
            };
          }
          return updateMessage(
            {
              ...state,
              isStreaming: false,
              activeAssistantId: null,
              streamError: { code: error.code, message: error.message },
            },
            targetAssistantId,
            (message) =>
              updateActiveVersion(message, (version) => ({
                ...version,
                status: "error",
                streamPhase: undefined,
                error: { code: error.code, message: error.message },
                statusHistory: appendStatusEntry(version.statusHistory, {
                  label: "Error",
                  state: "error",
                  detail: error.message,
                }),
              })),
          );
        }

        case "done":
          if (!targetAssistantId) {
            return { ...state, isStreaming: false, activeAssistantId: null };
          }
          return updateMessage(
            { ...state, isStreaming: false, activeAssistantId: null },
            targetAssistantId,
            (message) =>
              updateActiveVersion(message, (version) => ({
                ...version,
                status: "ready",
                streamPhase: undefined,
                artifacts: extractArtifactsFromContent(version.content),
                statusHistory: appendStatusEntry(version.statusHistory, {
                  label: "Completed",
                  state: "completed",
                }),
              })),
          );
      }
      return state;
    }

    case "stream_finished":
      return { ...state, isStreaming: false, activeAssistantId: null };

    case "stream_failed": {
      const failedId = state.activeAssistantId;
      if (!failedId) {
        return { ...state, isStreaming: false, activeAssistantId: null, streamError: action.error };
      }
      return updateMessage(
        { ...state, isStreaming: false, activeAssistantId: null, streamError: action.error },
        failedId,
        (message) =>
          updateActiveVersion(message, (version) => ({
            ...version,
            status: "error",
            streamPhase: undefined,
            error: action.error,
            statusHistory: appendStatusEntry(version.statusHistory, {
              label: "Error",
              state: "error",
              detail: action.error.message,
            }),
          })),
      );
    }
  }

  return state;
}
